// Never-tuned clean Duplex accuracy, optionally restricted to named rungs.
//
//   node dev/rung-score.mjs <external.json> [...]
//   RUNGS="0.2625/0.2253,0.273/0.2253" node dev/rung-score.mjs <external.json> [...]
//   DUMP=1 ... to list every reading
//
// WHY THE RUNG FILTER MATTERS. Any experiment that changes the fit for SOME
// rungs has to be scored on those rungs only, or the readings it cannot
// possibly affect dilute the result into noise. That is the same fixed-
// population discipline as SCORE_EXCLUDE in dev/holdout-score.mjs, and the
// reason the rung-volume experiment could be measured at all: 121 readings on
// four rungs moved by 9 when those rungs were starved, which is significant,
// while the same 9 against all 347 would have looked like nothing.
//
// The rung is taken from the REFERENCE's own wire pair, not ours, so the
// population is fixed by the data rather than by what the model currently
// picks.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { stateFromReading, isClean, isModelledDuplex } from "./ref-state.mjs";

const mod = await load();
const want = new Set((process.env.RUNGS || "").split(",").map((x) => x.trim()).filter(Boolean));
const cal = mod.DUPLEX_PAIRS['3 3/4" inside 6"'].calibration;
const nOf = new Map(cal.map((c) => [`${c.outerWire}/${c.innerWire}`, c.n]));
const files = process.argv.slice(2);

if (!files.length) {
    console.error("usage: [RUNGS=a/b,c/d] node dev/rung-score.mjs <external.json> [...]");
    process.exit(1);
}

const rows = [];

for (const f of files) {
    let data;

    try {
        data = JSON.parse(readFileSync(f, "utf8"));
    } catch {
        console.error(`skipping ${f} - unreadable`);
        continue;
    }

    for (const r of data) {
        const i = r.input, d = r.data;

        if (!d || r.error || !isModelledDuplex(i) || !isClean(r)) continue;

        const inn = d.innerSpring, out = d.outerSpring;

        if (!inn?.springLength || !out?.wireSize) continue;

        const refRung = `${parseFloat(out.wireSize)}/${parseFloat(inn.wireSize)}`;

        if (want.size && !want.has(refRung)) continue;

        const c = make(mod, stateFromReading(i));
        const s = c.duplexStep;

        if (!s) continue;

        const wireOk = `${s.outerWire}/${s.innerWire}` === refRung;

        rows.push({
            refRung, wireOk, n: nOf.get(refRung) ?? 0,
            exact: wireOk && c.duplexInnerLength === inn.springLength,
            key: [i.drum, i.springs, i.radius, i.lift, i.hiLift ?? "",
                i.cycles, i.weight, i.heightInches].join("|"),
        });
    }
}

const w = rows.filter((r) => r.wireOk);
const ok = w.filter((r) => r.exact).length;

console.log(`scored ${rows.length}   wire ok ${w.length}   length exact ${ok}/${w.length}`
    + ` = ${w.length ? (100 * ok / w.length).toFixed(2) : "-"}%`);

if (process.env.DUMP) {
    for (const r of rows) {
        console.log(`${r.exact ? "OK  " : "MISS"} ${r.refRung.padEnd(14)}`
            + ` n${String(r.n).padStart(4)} ${r.key}`);
    }
}
