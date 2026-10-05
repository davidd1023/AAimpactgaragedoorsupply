// The SINGLE path against an EXTERNAL random sample.
//
// dev/single-check.mjs only ever checked the multiplier, and only on readings
// chosen by hand - it scored 12/12 and was taken as proof the path was sound.
// The 725-case golden snapshot proves only that nothing MOVED. Neither answers
// whether Single is right, and on a uniform draw from the allowed box it is
// not.
//
// The reference picks the wire itself, so its own choice is fed back in and the
// length compared on equal terms.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
// The reference encodes our "LHR" low-headroom track as radius 10. Passing
// "10" straight through gives the app a radius it does not offer, so
// radiusTurnDrop finds no curve, drops no turns, and every radius-10 reading
// fails - 0 of 54, which looked exactly like a broken LHR curve in the app.
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};
let n = 0, mult = 0, raw = 0, q4 = 0, q8 = 0;
const rel = [];

for (const file of process.argv.slice(2)) {
    let rows;

    try {
        rows = JSON.parse(readFileSync(file, "utf8"));
    } catch {
        continue;
    }

    for (const r of rows) {
        const i = r.input;

        if (r.error || !r.data || i.assembly !== "Single") {
            continue;
        }

        // HI-LIFT IS SCORED, not skipped. It was skipped because there was no
        // hi-lift Single data to score - eval-single.json was 176 readings of
        // pure standard lift, so the Single figures quoted from here said
        // nothing at all about hi-lift. That is how a wrong assembly hardware
        // constant survived in the Single path: the one number that would have
        // caught it was never measured. The readings exist now, so they count.
        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";

        if (i.lift && !hi && i.lift !== "Standard") {
            continue;
        }

        const sp = r.data.innerSpring ?? r.data.outerSpring;

        if (!sp || !sp.springLength || !ID_TEXT[sp.innerDiameter]) {
            continue;
        }

        const c = make(mod, {
            assembly: "Single", drum: i.drum, springId: ID_TEXT[sp.innerDiameter],
            springs: i.springs ?? 2, radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            wireSize: `${sp.wireSize}"`,
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight), doorWidthFeet: 9,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const ex = c.springLengthExact;

        if (!(ex > 0)) {
            continue;
        }

        n += 1;
        rel.push((c.multiplierExact - r.data.multiplier) / r.data.multiplier);

        if (Math.abs(c.multiplierExact - r.data.multiplier) < 2e-5) mult += 1;
        if (Math.abs(c.springLength - sp.springLength) < 1e-9) raw += 1;
        if (Math.abs(Math.round(ex * 4) / 4 - sp.springLength) < 1e-9) q4 += 1;
        if (Math.abs(Math.round(ex * 8) / 8 - sp.springLength) < 1e-9) q8 += 1;
    }
}

rel.sort((a, b) => a - b);
const pct = (k) => `${(k / n * 100).toFixed(1)}%`;
console.log(`SINGLE against ${n} external readings`);
console.log(`  multiplier within 2e-5        ${mult}/${n}  ${pct(mult)}`);
console.log(`  multiplier relative error     p10 ${(rel[Math.floor(n * 0.1)] * 100).toFixed(2)}%` +
    `  median ${(rel[Math.floor(n / 2)] * 100).toFixed(3)}%` +
    `  p90 ${(rel[Math.floor(n * 0.9)] * 100).toFixed(2)}%`);
console.log(`  length as returned today      ${raw}/${n}  ${pct(raw)}`);
console.log(`  length rounded to 1/4"        ${q4}/${n}  ${pct(q4)}`);
console.log(`  length rounded to 1/8"        ${q8}/${n}  ${pct(q8)}`);
