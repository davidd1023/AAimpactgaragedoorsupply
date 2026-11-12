// IS THE PAST-120" DRIFT A CORRECTABLE RULE, OR JUST EXTRAPOLATION NOISE?
//
//   node dev/over120-fit.mjs
//
// dev/over120.mjs found what the three "this would count as support" tests
// were looking for:
//
//   - the error is ASYMMETRIC - 143 long against 4 short, so we overshoot
//   - it GROWS with distance past 120": 78.7% exact just over the line,
//     0.0% exact more than 100" past it, median +2.00
//
// A flat offset cannot fix a growing error, and the measurement agrees (44.1%
// as it stands, nothing better at any constant). So the candidate is a
// LENGTH-DEPENDENT correction, which is what a drift wants.
//
// WHY A DRIFT IS EXPECTED HERE RATHER THAN SURPRISING. The bonus table is
// keyed on floor(active length), and the corpus thins out as springs get
// long, so at 200"+ the fitter is EXTRAPOLATING a rung line past its data.
// Extrapolation error that grows with distance is the signature of exactly
// that - which also means it may be a property of the fit rather than a rule
// of the reference, and those are fixed differently.
//
// THE TEST IS SPLIT-HALF, NOT IN-SAMPLE. The previous script's per-rung
// offset reached 64% in-sample against 44% flat, and in-sample is how every
// losing idea in this project first looked promising. A correction is only
// worth shipping if it survives being fitted on data it is not then scored
// on, so this fits on one half and scores on the other, both ways round.
//
// AND THE GRID IS {n, n+0.25}, so a correction has to land on it - a
// continuous nudge that lands between the rungs the reference actually uses
// cannot be right even when it is closer.
import { readFileSync } from "node:fs";
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

    const step = c.duplexStep;

    if (!step) continue;
    if (`${step.outerWire}/${step.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const refMax = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);

    if (refMax <= 120) continue;

    rows.push({
        ourIn: c.duplexInnerLength, ourOut: c.duplexOuterLength,
        refIn: r.expect.duplexInnerLength, refOut: r.expect.duplexOuterLength,
        // the correction is keyed on OUR OWN length, because at prediction
        // time the reference's is exactly what is not known
        L: c.duplexInnerLength,
        act: c.duplexActiveLength,
        rung: `${step.outerWire}/${step.innerWire}`,
        springs: c.duplexSpringCount,
    });
}

console.log(`${rows.length} past-120" readings with the wire right\n`);

// Correct, then snap back onto the grid the reference actually uses.
const snap = (x) => {
    const lo = Math.floor(x);
    return [lo, lo + 0.25, lo + 1].reduce((a, b) =>
        (Math.abs(b - x) < Math.abs(a - x) ? b : a));
};
const score = (set, f) => set.filter((x) =>
    snap(x.ourIn - f(x)) === x.refIn && snap(x.ourOut - f(x)) === x.refOut).length;

// --- fit a linear drift  d = a + b*(L - 120)  by a coarse grid search, since
// the objective is a COUNT of exact matches and not a least-squares residual.
// Fitting the mean would optimise the wrong thing: being 0.4" closer on
// average is worth nothing if it lands between grid points.
const fit = (train) => {
    let best = { a: 0, b: 0, hit: score(train, () => 0) };

    for (let a = -1; a <= 3.001; a += 0.25) {
        for (let b = 0; b <= 0.05001; b += 0.0025) {
            const hit = score(train, (x) => a + b * (x.L - 120));

            if (hit > best.hit) best = { a, b, hit };
        }
    }

    return best;
};

const { rnd } = makeRnd(20261111);
const sh = rows.slice();

for (let i = sh.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));

    [sh[i], sh[j]] = [sh[j], sh[i]];
}

const half = Math.floor(sh.length / 2);
const A = sh.slice(0, half), B = sh.slice(half);

console.log("SPLIT-HALF: fit on one half, score on the OTHER\n");
console.log("  fitted on   a      b        train     TEST (out of sample)   baseline");

let gained = 0;

for (const [train, test, name] of [[A, B, "half A"], [B, A, "half B"]]) {
    const f = fit(train);
    const g = (x) => f.a + f.b * (x.L - 120);
    const testHit = score(test, g);
    const base = score(test, () => 0);

    gained += testHit - base;
    console.log(`  ${name}      ${f.a.toFixed(2).padStart(5)}  ${f.b.toFixed(4)}   `
        + `${(f.hit / train.length * 100).toFixed(1).padStart(5)}%    `
        + `${(testHit / test.length * 100).toFixed(1).padStart(5)}%  `
        + `(${testHit}/${test.length})        `
        + `${(base / test.length * 100).toFixed(1).padStart(5)}%`);
}

console.log(`\n  net readings gained out of sample: ${gained >= 0 ? "+" : ""}${gained}`
    + ` of ${rows.length}`);

// --- the per-rung version, also split-half, because a global drift may be
// hiding real per-rung behaviour the way one E hid fifty rung lines.
console.log("\nPER-RUNG, same split-half protocol\n");

let gainedR = 0;

for (const [train, test, name] of [[A, B, "half A"], [B, A, "half B"]]) {
    const offs = new Map();

    for (const rg of new Set(train.map((x) => x.rung))) {
        offs.set(rg, fit(train.filter((x) => x.rung === rg)));
    }

    const g = (x) => {
        const f = offs.get(x.rung);
        return f ? f.a + f.b * (x.L - 120) : 0;
    };
    const testHit = score(test, g);
    const base = score(test, () => 0);

    gainedR += testHit - base;
    console.log(`  fitted on ${name}   TEST ${(testHit / test.length * 100).toFixed(1)}% `
        + `(${testHit}/${test.length})   baseline ${(base / test.length * 100).toFixed(1)}%`);
}

console.log(`\n  net readings gained out of sample: `
    + `${gainedR >= 0 ? "+" : ""}${gainedR} of ${rows.length}`);
console.log("\n  A correction worth shipping gains on data it was not fitted to.");
console.log("  A negative or near-zero number means the drift is extrapolation");
console.log("  noise, not a rule - and there is nothing here to take.");
