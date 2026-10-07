// How well we reproduce the reference's DRUM MULTIPLIER, per drum.
//
//   node dev/mult-survey.mjs
//
// WHY SEPARATELY FROM LENGTH. The multiplier is upstream of everything: turns,
// TIPPT, spring length and cycle life all come off it. But it is also reported
// by the reference on every reading, including the ones it flags - the flag is
// about the spring it chose, not about the drum arithmetic - so this question
// has roughly twice the data that length accuracy does, and a wrong multiplier
// explains a length miss in a way the length alone cannot show.
//
// WHAT IT FOUND, AND WHY THAT DID NOT BECOME A FIX. The D800-120 hi-lift
// surface reproduces only 4.7% of its geometries exactly and is off by as much
// as 1.7e-03, which is about twenty times the error that can flip a TIPPT
// rounding and with it a whole inch of spring. That looks like the obvious
// next fix. It is not: on the validation sample every single clean length miss
// has an EXACTLY correct TIPPT, so repairing the surface would not move the
// figure that matters. It is a real inaccuracy with no measurable consequence
// yet - worth knowing, worth watching, not worth fitting.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { stateFromReading, isHiLift, isModelledDuplex, REF_RADIUS } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const OFFERED = new Set([...Object.keys(mod.DRUMS), ...Object.keys(mod.HILIFT_DRUMS)]);
const rows = [];
const seen = new Set();

for (const f of readdirSync(HERE).filter((x) => /\.json$/.test(x))) {
    let data;

    try {
        data = JSON.parse(readFileSync(join(HERE, f), "utf8"));
    } catch {
        continue;
    }

    const list = Array.isArray(data) ? data : (data.readings ?? []);

    if (!Array.isArray(list)) {
        continue;
    }

    for (const r of list) {
        const i = r?.input;

        if (!i || r.error || typeof r.data?.multiplier !== "number") continue;
        if (!isModelledDuplex(i) || !i.heightInches) continue;

        const hi = isHiLift(i);

        // ONLY WHAT THE MODULE OFFERS. The pulls include a handful of probes
        // on other drums and on a 20" track radius, taken to read the
        // reference's own limits back. We model six drums and three radii, so
        // those readings measure nothing about this model - left in, they
        // showed up as an 8.6e-02 "error" on a drum that was never wrong.
        if (!OFFERED.has(i.drum)) continue;
        if (!(Number(i.radius) in REF_RADIUS)) continue;

        // PAST A DRUM'S OWN RATING IS NOT AN ERROR EITHER. The reference will
        // extrapolate its curves above a drum's published hi-lift and height -
        // on the D800-120 it returns negative multipliers - and this module
        // refuses instead, deliberately, because a confident wrong answer is
        // worse than none. Scoring those readings measures the refusal, not
        // the model: a 54" drum read at 90" of hi-lift was the whole of the
        // 525-54HL's worst case.
        const limits = mod.HILIFT_DRUMS[i.drum];

        if (hi && limits) {
            if (Number(i.hiLift) > limits.maxHiLift) continue;
            if (limits.maxHeight && i.heightInches > limits.maxHeight) continue;
        }

        // The multiplier depends on the drum and the door geometry only, so
        // one reading per distinct geometry is all the information there is.
        const key = `${i.drum}|${hi ? i.hiLift : "std"}|${i.heightInches}|${i.radius}`;

        if (seen.has(key)) continue;

        seen.add(key);

        const ours = make(mod, stateFromReading(i)).multiplier;

        if (typeof ours !== "number" || !isFinite(ours)) continue;

        rows.push({ drum: `${i.drum.split(" ").pop()} ${hi ? "hi-lift" : "standard"}`,
                    d: ours - r.data.multiplier, height: i.heightInches, hiLift: i.hiLift, hi });
    }
}

const by = new Map();

for (const r of rows) {
    if (!by.has(r.drum)) by.set(r.drum, []);
    by.get(r.drum).push(r);
}

console.log(`${rows.length} distinct drum/door geometries reporting a multiplier\n`);
console.log("drum                      n    exact   over 1e-5    worst      at");

for (const [k, set] of [...by].sort()) {
    const exact = set.filter((r) => Math.abs(r.d) <= 5e-7).length;
    const off = set.filter((r) => Math.abs(r.d) > 1e-5).length;
    const worst = set.slice().sort((a, b) => Math.abs(b.d) - Math.abs(a.d))[0];

    console.log(`${k.padEnd(22)} ${String(set.length).padStart(4)}  `
        + `${(100 * exact / set.length).toFixed(1).padStart(5)}%  ${String(off).padStart(9)}  `
        + `${worst.d.toExponential(2).padStart(9)}   ${worst.height}in${worst.hi ? ` hl${worst.hiLift}` : ""}`);
}
