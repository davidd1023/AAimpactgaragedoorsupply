// FIT THE PAST-120" LENGTH CORRECTION, AND PROVE IT OUT OF SAMPLE FIRST.
//
//   node dev/derive-over120.mjs            measure, choose the guard, emit
//   node dev/derive-over120.mjs --emit     print the table only
//
// WHAT THIS CORRECTS AND WHY IT IS ALLOWED TO EXIST.
//
// Past 120" the model OVERSHOOTS: 143 readings long against 4 short, median
// +1.00, and the error GROWS with length - 78.7% exact just over the line,
// 0.0% exact more than 100" past it. The reference disclaims this band in its
// own words ("only spring lengths between 0 and 120" are supported"), which
// is exactly why a local correction is defensible here and nowhere else.
//
// THE OVERSHOOT IS NOT IN THE BONUS. Each rung's bonus is clamped to two
// levels (`lo`/`hi` in lineByCount), at most about an inch - it cannot
// produce a 2" drift. So the error is in `duplexActiveLength`, which is the
// stiffness model, and correcting THAT would move all 11,564 in-envelope
// readings that are right today. A correction gated above 120" cannot: that
// is the whole argument for doing it this way round, and it is why the ugly
// local fix is the safe one here and the principled one is not.
//
// MEASURED, NOT ASSUMED, by split-half - fit on one half, score on the other,
// both ways round:
//
//     baseline (no correction)        116 / 263   44.1%
//     per-rung LINEAR    (~64 params) 137 / 263   52.1%
//     per-rung CONSTANT  (~32 params) 148 / 263   56.3%   <- simpler AND better
//
// The simpler form winning is the useful result: a line per rung has twice
// the freedom and does worse on data it was not fitted to, which is the same
// lesson as LINE_LEVELS and the per-group capacity experiment.
//
// THE GATE IS OUR OWN LENGTH, NOT THE REFERENCE'S. At prediction time the
// reference's answer is precisely what is unknown, so banding on it would be
// a tool that cannot be shipped. Outer is always inner + 1, so "the pair goes
// past 120" is `inner > 119`.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { makeRnd } from "./rnd.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const s = c.duplexStep;

    if (!s) continue;

    // A wire miss is a different spring; its length is not comparable.
    if (`${s.outerWire}/${s.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const ourIn = c.duplexInnerLength;

    if (!(ourIn > 119)) continue;      // the runtime gate, applied here too

    rows.push({
        ourIn, ourOut: c.duplexOuterLength,
        refIn: r.expect.duplexInnerLength, refOut: r.expect.duplexOuterLength,
        rung: `${s.outerWire}/${s.innerWire}`,
    });
}

// The grid the reference actually uses - whole inches and quarters, never a
// half, never three quarters, in 20,344 readings.
const snap = (x) => {
    const lo = Math.floor(x);
    return [lo, lo + 0.25, lo + 1].reduce((a, b) =>
        (Math.abs(b - x) < Math.abs(a - x) ? b : a));
};
// Correcting the inner carries the outer, which is always inner + 1.
const hit = (x, off) => snap(x.ourIn - off) === x.refIn
    && snap(x.ourOut - off) === x.refOut;
const score = (set, offs) => set.filter((x) =>
    hit(x, offs.get(x.rung) ?? 0)).length;

const OFFSETS = [];

for (let a = -1; a <= 4.001; a += 0.25) OFFSETS.push(Math.round(a * 100) / 100);

// A rung with too few readings is a constant fitted to noise, so the guard is
// a MINIMUM COUNT below which the rung is left alone. Which minimum is itself
// measured rather than picked.
const fitOffsets = (train, min) => {
    const out = new Map();

    for (const rg of new Set(train.map((x) => x.rung))) {
        const g = train.filter((x) => x.rung === rg);

        if (g.length < min) continue;

        let best = 0, bestHit = g.filter((x) => hit(x, 0)).length;

        for (const off of OFFSETS) {
            const h = g.filter((x) => hit(x, off)).length;

            if (h > bestHit) { bestHit = h; best = off; }
        }

        if (best !== 0) out.set(rg, best);
    }

    return out;
};

console.log(`${rows.length} past-120" readings with the wire right, `
    + `${new Set(rows.map((x) => x.rung)).size} rungs\n`);

const { rnd } = makeRnd(20261111);
const sh = rows.slice();

for (let i = sh.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));

    [sh[i], sh[j]] = [sh[j], sh[i]];
}

const half = Math.floor(sh.length / 2);
const A = sh.slice(0, half), B = sh.slice(half);

console.log("CHOOSING THE MINIMUM-READINGS GUARD, split-half (out of sample)\n");
console.log("  min   rungs kept   exact out of sample");

let bestMin = 1, bestTotal = -1;

for (const min of [1, 2, 3, 4, 5, 6, 8, 10]) {
    let tot = 0, kept = 0;

    for (const [train, test] of [[A, B], [B, A]]) {
        const offs = fitOffsets(train, min);

        kept += offs.size;
        tot += score(test, offs);
    }

    if (tot > bestTotal) { bestTotal = tot; bestMin = min; }

    console.log(`  ${String(min).padStart(3)}   ${String(kept / 2).padStart(9)}   `
        + `${String(tot).padStart(4)} / ${rows.length}  `
        + `${(tot / rows.length * 100).toFixed(1).padStart(5)}%`);
}

const base = score(A, new Map()) + score(B, new Map());

console.log(`  none  ${String(0).padStart(9)}   ${String(base).padStart(4)} / `
    + `${rows.length}  ${(base / rows.length * 100).toFixed(1).padStart(5)}%  <- baseline`);
console.log(`\n  best guard: min ${bestMin} readings per rung, `
    + `+${bestTotal - base} readings out of sample\n`);

// The shipped table is fitted on EVERYTHING, which is right - the split-half
// above establishes that the FORM generalises, and the final fit should then
// use all the data. Scoring it on the same data would be meaningless and is
// not done.
const final = fitOffsets(rows, bestMin);

console.log(`SHIPPED TABLE: ${final.size} rungs carry an offset `
    + `(the rest are left alone)\n`);

const js = "{ " + [...final].sort()
    .map(([k, v]) => `"${k}": ${v}`).join(", ") + " }";

console.log(js);
writeFileSync(join(HERE, "over120-offsets.json"),
    JSON.stringify(Object.fromEntries(final), null, 1) + "\n");
console.log(`\nwritten to dev/over120-offsets.json`);
console.log(`in-sample with this table: `
    + `${(score(rows, final) / rows.length * 100).toFixed(1)}% `
    + `(optimistic by construction - quote the split-half figure)`);
