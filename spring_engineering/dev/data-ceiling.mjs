// WOULD MORE READINGS FIX THE LENGTH RULE, AND HOW MANY WOULD IT TAKE?
//
//   node dev/data-ceiling.mjs            the learning curve
//   node dev/data-ceiling.mjs groups     how the key space is filling up
//
// ASKED BECAUSE SOMEBODY PROPOSED A MILLION PULLS. That is a fair question
// and it deserves a measurement rather than an opinion - but it is also a
// 1.8 GB download on a 1 GB disk and eleven days at the one-request-a-second
// courtesy rate, so it is worth knowing what it would buy BEFORE starting.
//
// AND IT IS NOT THE SAME QUESTION BATCH S2 ANSWERED. S2 showed that filling
// a rung 2.6x does not help THE FITTER - the bonus table is a model with
// limited capacity and it was already saturated. The interesting idea in "a
// million readings" is different and genuinely new: with enough coverage you
// do not NEED a fitter. You look the answer up.
//
// So this measures the LOOKUP, not the fit:
//
//     key    = (rung, spring count, floor of active length)
//     within that key the bonus is a step function of frac, so a test
//     reading takes the bonus of the NEAREST frac seen in training
//
// That is the best any amount of data could do without a new idea, because
// it is what infinite data converges to. If the lookup's curve is still
// climbing steeply at the full corpus, more readings pay. If it has
// flattened below the fitted table, they do not - and a million would buy
// eleven days of nothing.
//
// THE CURVE IS THE POINT, NOT THE ENDPOINT. One accuracy figure at one
// training size says nothing about what the next reading is worth; the slope
// does.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { makeRnd } from "./rnd.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));

// Extract once - building a component per reading is the slow part.
const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let comp;

    try { comp = make(mod, r.state); } catch { continue; }

    const step = comp.duplexStep;

    if (!step) continue;

    const refW = `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`;

    // WIRE-ONLY MISSES EXCLUDED. A different wire is a different spring and
    // its length is not comparable - every length diagnostic here does this.
    if (`${step.outerWire}/${step.innerWire}` !== refW) continue;

    const act = comp.duplexActiveLength;
    const floor = Math.floor(act);

    rows.push({
        key: `${refW}|${comp.duplexSpringCount}|${floor}`,
        frac: act - floor,
        bonus: r.expect.duplexInnerLength - floor,
        // what the INSTALLED table says, to compare like with like
        ourOk: comp.duplexInnerLength === r.expect.duplexInnerLength,
        flagged: !!r.flagged,
    });
}

console.log(`${rows.length} readings with the wire right `
    + `(${rows.filter((r) => !r.flagged).length} not flagged)\n`);

if (process.argv[2] === "groups") {
    // HOW THE KEY SPACE IS FILLING UP. A lookup needs enough frac samples
    // inside each key, so the shape that matters is readings-per-key.
    const per = new Map();

    for (const r of rows) per.set(r.key, (per.get(r.key) ?? 0) + 1);

    const counts = [...per.values()].sort((a, b) => a - b);
    const at = (p) => counts[Math.floor(counts.length * p)];

    console.log(`distinct keys: ${per.size}   readings per key: `
        + `p10 ${at(0.1)}  median ${at(0.5)}  p90 ${at(0.9)}  max ${counts.at(-1)}`);
    console.log(`keys with ONE reading: ${counts.filter((c) => c === 1).length} `
        + `(${(counts.filter((c) => c === 1).length / per.size * 100).toFixed(1)}%)`);

    // A key seen once teaches a lookup nothing it can check, so the share of
    // singletons is roughly how far the corpus is from dense.
    const contra = [...per.keys()].filter((k) => {
        const g = rows.filter((r) => r.key === k);
        const byFrac = new Map();

        for (const r of g) {
            const f = r.frac.toFixed(2);

            if (byFrac.has(f) && byFrac.get(f) !== r.bonus) return true;

            byFrac.set(f, r.bonus);
        }

        return false;
    });

    console.log(`keys that CONTRADICT themselves at the same frac: `
        + `${contra.length} - no amount of data fixes these`);
    process.exit(0);
}

// ---------------------------------------------------------------- the curve
const { rnd } = makeRnd(20261111);
const shuffled = rows.slice();

for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));

    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
}

// A fifth held out, never trained on, the same for every training size - so
// the only thing changing along the curve is how much the lookup has seen.
const cut = Math.floor(shuffled.length * 0.2);
const test = shuffled.slice(0, cut);
const pool = shuffled.slice(cut);

const lookup = (train) => {
    const idx = new Map();

    for (const r of train) {
        if (!idx.has(r.key)) idx.set(r.key, []);

        idx.get(r.key).push(r);
    }

    let hit = 0, covered = 0;

    for (const t of test) {
        const g = idx.get(t.key);

        if (!g) continue;      // key never seen - the lookup has no answer

        covered++;

        let best = g[0];

        for (const c of g) {
            if (Math.abs(c.frac - t.frac) < Math.abs(best.frac - t.frac)) best = c;
        }

        if (best.bonus === t.bonus) hit++;
    }

    return {
        covered: covered / test.length,
        // accuracy COUNTING AN UNCOVERED KEY AS WRONG, which is what a
        // deployed lookup would have to do - it cannot decline to answer.
        acc: hit / test.length,
        // and among the ones it could answer at all
        accCovered: covered ? hit / covered : 0,
    };
};

console.log("LOOKUP LEARNING CURVE   (test = a fifth held out, never trained on)");
console.log("  train      n    key seen   exact (all)   exact (where seen)");

const fracs = [0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.7, 0.85, 1];

for (const f of fracs) {
    const n = Math.floor(pool.length * f);
    const r = lookup(pool.slice(0, n));

    console.log(`  ${(f * 100).toFixed(0).padStart(4)}%  ${String(n).padStart(6)}`
        + `     ${(r.covered * 100).toFixed(1).padStart(5)}%`
        + `       ${(r.acc * 100).toFixed(2).padStart(6)}%`
        + `            ${(r.accCovered * 100).toFixed(2).padStart(6)}%`);
}

const table = test.filter((t) => t.ourOk).length / test.length;

console.log(`\n  THE INSTALLED TABLE on these same held-out readings: `
    + `${(table * 100).toFixed(2)}%`);
console.log("\n  A lookup is what infinite data converges to. Read the SLOPE of");
console.log("  the last few rows: that is what the next reading is worth.");
