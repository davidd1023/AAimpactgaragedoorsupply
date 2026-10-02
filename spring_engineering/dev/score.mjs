// Score one or more pulls against the shipped model, grouped by drum/radius/lift.
//
//   node dev/score.mjs dev/pulled-k3.json [more.json ...]
//
// replay.mjs asserts the corpus; this is for a pull you have NOT imported yet,
// to see what a batch says before it changes the calibration. It separates the
// three things that can be wrong - multiplier (geometry), wire (the ladder and
// K), length (the bands) - because they have completely different causes and
// lumping them together hides which one moved.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
// The reference encodes our "LHR" low-headroom track as radius 10.
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
let N = 0, M = 0, W = 0, L = 0;
const groups = {};

for (const file of process.argv.slice(2)) {
    for (const r of JSON.parse(readFileSync(file, "utf8"))) {
        const i = r.input;

        if (r.error || !r.data || !r.data.innerSpring || !r.data.outerSpring) {
            continue;
        }

        const d = r.data;
        const ri = d.innerSpring;
        const ro = d.outerSpring;
        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, {
            assembly: "Duplex", drum: i.drum, springId: '3 3/4" inside 6"',
            springs: i.springs,
            radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
            doorWidthInches: (i.widthInches ?? 108) % 12,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const s = c.duplexStep;
        const refW = `${ro.wireSize}/${ri.wireSize}`;
        const ourW = s ? `${s.outerWire}/${s.innerWire}` : "none";
        const mok = Math.abs(c.multiplierExact - d.multiplier) < 2e-5;
        const wok = refW === ourW;
        const lok = wok && c.duplexInnerLength === ri.springLength;

        N += 1;
        M += mok ? 1 : 0;
        W += wok ? 1 : 0;
        L += lok ? 1 : 0;

        const key = `${i.drum.split(" ").pop()}  r${i.radius}${hi ? " hi-lift" : ""}`;
        const g = groups[key] ??= { n: 0, m: 0, w: 0, l: 0, bad: [] };

        g.n += 1;
        g.m += mok ? 1 : 0;
        g.w += wok ? 1 : 0;
        g.l += lok ? 1 : 0;

        if (!wok || !lok) {
            g.bad.push(
                `      ${i.weight}lb ${i.heightInches}in ${i.springs}spr t${i.cycles}` +
                `  ${refW} vs ${ourW}  L ${ri.springLength} vs ${c.duplexInnerLength}`
            );
        }
    }
}

console.log(`${N} scored:  multiplier ${M}/${N}   wire ${W}/${N}   length ${L}/${N}\n`);

for (const k of Object.keys(groups).sort()) {
    const g = groups[k];

    console.log(
        `  ${k.padEnd(26)} n=${String(g.n).padStart(3)}  ` +
        `mult ${g.m}/${g.n}  wire ${g.w}/${g.n}  length ${g.l}/${g.n}`
    );

    if (g.bad.length) {
        console.log(g.bad.slice(0, 8).join("\n"));

        if (g.bad.length > 8) {
            console.log(`      ... and ${g.bad.length - 8} more`);
        }
    }
}
