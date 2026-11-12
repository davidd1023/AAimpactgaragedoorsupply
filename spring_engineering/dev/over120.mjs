// CAN THE DUPLEX LENGTHS PAST 120" BE IMPROVED?
//
//   node dev/over120.mjs
//
// THE BAND THE REFERENCE DISCLAIMS. dev/envelope.mjs splits duplex by the
// reference's own words - "only spring lengths between 0 and 120" are
// supported" - and the band past that scores 43.28% exact against 98.06%
// inside 96". The wire is still right 98.13% of the time there, so the whole
// shortfall is LENGTH.
//
// WHY IT MIGHT BE FIXABLE WHERE THE REST IS NOT. Every previous lever was
// tried on the model as a WHOLE and lost because it traded good answers for
// bad ones. A correction that fires ONLY above 120" cannot regress anything
// below it - the 11,564 readings inside the recommended band are untouched by
// construction. So this is the one place where a cheap, ugly, local rule is
// allowed, if the data supports one.
//
// WHAT WOULD COUNT AS SUPPORT, decided before looking:
//
//  - A SYSTEMATIC BIAS. If we are consistently short by about the same amount
//    past 120", that is a correction. A symmetric spread is not - the duplex
//    wire work established that a symmetric error is a boundary being crossed
//    both ways and no shift can win.
//  - CLAMPING. If the reference's lengths pile up at one value, it is capping
//    rather than computing, and we should cap too.
//  - DRIFT WITH DISTANCE. If the error grows with how far past 120" the
//    spring is, the rule changes there rather than simply being noisier.
//
// Anything else and the answer is no.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));

const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const step = c.duplexStep;

    if (!step) continue;

    // WIRE MISSES EXCLUDED - a different wire is a different spring and its
    // length is not comparable. 98.13% of this band has the wire right, so
    // almost nothing is lost.
    if (`${step.outerWire}/${step.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const refMax = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);

    rows.push({
        band: refMax <= 96 ? "in" : refMax <= 120 ? "mid" : "over",
        refMax,
        past: refMax - 120,
        dIn: c.duplexInnerLength - r.expect.duplexInnerLength,
        dOut: c.duplexOuterLength - r.expect.duplexOuterLength,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
        refIn: r.expect.duplexInnerLength,
        rung: `${step.outerWire}/${step.innerWire}`,
        springs: c.duplexSpringCount,
    });
}

const med = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
};

console.log("1. IS THERE A SYSTEMATIC BIAS?  (ours - reference, inner length)\n");
console.log("  band      n    exact    median d    mean d    short   long   p10     p90");

for (const b of ["in", "mid", "over"]) {
    const g = rows.filter((x) => x.band === b);

    if (!g.length) continue;

    const ds = g.map((x) => x.dIn);
    const sorted = ds.slice().sort((a, b2) => a - b2);
    const mean = ds.reduce((a, b2) => a + b2, 0) / ds.length;

    console.log(`  ${b.padEnd(6)}${String(g.length).padStart(6)}  `
        + `${(g.filter((x) => x.ok).length / g.length * 100).toFixed(1).padStart(5)}%  `
        + `${med(ds).toFixed(2).padStart(8)}  ${mean.toFixed(2).padStart(8)}  `
        + `${String(ds.filter((d) => d < 0).length).padStart(5)}  `
        + `${String(ds.filter((d) => d > 0).length).padStart(5)}  `
        + `${sorted[Math.floor(ds.length * 0.1)].toFixed(2).padStart(6)}  `
        + `${sorted[Math.floor(ds.length * 0.9)].toFixed(2).padStart(6)}`);
}

const over = rows.filter((x) => x.band === "over");

console.log(`\n2. IS THE REFERENCE CLAMPING?  commonest lengths it returns past 120"\n`);

const byLen = new Map();

for (const x of over) byLen.set(x.refMax, (byLen.get(x.refMax) ?? 0) + 1);

console.log("  " + [...byLen].sort((a, b) => b[1] - a[1]).slice(0, 10)
    .map(([k, v]) => `${k}":${v}`).join("  "));
console.log(`  ${byLen.size} distinct lengths over ${over.length} readings - `
    + `${byLen.size > over.length / 3 ? "SPREAD, not clamped" : "piled up, possibly clamped"}`);

console.log(`\n3. DOES THE ERROR GROW WITH DISTANCE PAST 120"?\n`);
console.log("  past 120    n    exact    median d");

for (const [lo, hi] of [[0, 10], [10, 25], [25, 50], [50, 100], [100, 1e9]]) {
    const g = over.filter((x) => x.past > lo && x.past <= hi);

    if (!g.length) continue;

    console.log(`  ${`${lo}-${hi === 1e9 ? "+" : hi}"`.padEnd(10)}${String(g.length).padStart(5)}  `
        + `${(g.filter((x) => x.ok).length / g.length * 100).toFixed(1).padStart(5)}%  `
        + `${med(g.map((x) => x.dIn)).toFixed(2).padStart(8)}`);
}

console.log(`\n4. WOULD A FLAT OFFSET HELP?  (applied only above 120")\n`);
console.log("  offset   exact after");

for (const off of [-2, -1.5, -1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 1, 1.5, 2]) {
    const hit = over.filter((x) => x.dIn - off === 0 && x.dOut - off === 0).length;

    console.log(`  ${off.toFixed(2).padStart(6)}   `
        + `${(hit / over.length * 100).toFixed(2).padStart(6)}%`
        + (off === 0 ? "   <- as it stands" : ""));
}

// THE HONEST CHECK. A per-rung offset has far more freedom than a flat one
// and will always look better in-sample; if even THAT cannot reach a useful
// figure, no offset rule exists here.
const rungs = [...new Set(over.map((x) => x.rung))];
let best = 0;

for (const rg of rungs) {
    const g = over.filter((x) => x.rung === rg);
    let b = 0;

    for (const off of [-3, -2.5, -2, -1.5, -1, -0.75, -0.5, -0.25, 0,
        0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3]) {
        const hit = g.filter((x) => x.dIn - off === 0 && x.dOut - off === 0).length;

        if (hit > b) b = hit;
    }

    best += b;
}

console.log(`\n  best offset chosen PER RUNG, in-sample: `
    + `${(best / over.length * 100).toFixed(2)}%  over ${rungs.length} rungs`);
console.log("  (in-sample and therefore optimistic - if this is not far above");
console.log("   the flat figure, there is no offset rule to find.)");
