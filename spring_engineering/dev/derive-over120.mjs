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
//     baseline (no correction)                   46.4%
//     per-rung LINEAR            (~64 params)    52.1%
//     per-rung CONSTANT          (~32 params)    53.2%
//     per-rung TWO LEVELS on floor (~75 params)  59.3%   <- shipped
//
// TWELVE FORMS, ELEVEN OF WHICH LOST TO THE CONSTANT. The twelfth is the only
// one that came out of a measurement rather than out of invention: past the
// gate every rung's implied bonus takes exactly TWO LEVELS ONE INCH APART
// (`-1`/`0` on the heavy rungs, `0.25`/`1.25` on `0.2625/0.2253 4spr`), never
// a spread, so a single constant can only pick the majority level - which is
// exactly the 53% it scored.
//
// THE SEPARATOR IS THE FLOOR OF THE ACTIVE LENGTH. Frac, door height, weight
// and cycle count were all tried; floor is the only one that generalises, and
// it is the same variable `splitByCount` splits on in-envelope. Out here the
// bonus line is clamped to two levels and SATURATES, so the second level it
// wants cannot be reached and has to be supplied by this table.
//
// FIVE SHUFFLES, FIVE WINS, +6.14 points pooled over 3,030 out-of-sample
// scorings. Simpler is usually better in this project - LINE_LEVELS, the
// per-group capacity experiment, the per-rung line above - and this is the
// one place where it was not, because the extra freedom was measured to be
// needed rather than hoped to be.
//
// EMPTY THE INSTALLED TABLE BEFORE FITTING. THIS IS NOT OPTIONAL.
//
// The gate below reads `c.duplexInnerLength`, which is the engine's output
// AFTER DUPLEX_LONG_OFFSET has already been applied. Fit against that and you
// are fitting a correction on top of itself: on 2026-11-12 this script was run
// with the offsets still installed and reported "0 rungs carry an offset,
// baseline 61.5%" - which read as "the correction is no longer needed". It was
// needed. Emptying the table and measuring put the band straight back to
// 43.28%, and refitting properly returned twelve rungs worth +42 readings.
//
// So the order is: EMPTY the block in spring_engineering.js, run this, then
// install what it writes. `sh dev/apply-over120.sh` does all three.
//
// The same family as reading a getter after changing its inputs underneath
// it - a correct measurement of the wrong thing. A derived correction must be
// fitted against output that does not already contain it.
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
        floor: Math.floor(c.duplexActiveLength),
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
    hit(x, offFor(entryFor(offs, x), x))).length;

const OFFSETS = [];

for (let a = -1; a <= 4.001; a += 0.25) OFFSETS.push(Math.round(a * 100) / 100);

const bestOffset = (g) => {
    let best = 0, bestHit = g.filter((x) => hit(x, 0)).length;

    for (const off of OFFSETS) {
        const h = g.filter((x) => hit(x, off)).length;

        if (h > bestHit) { bestHit = h; best = off; }
    }

    return [best, bestHit];
};

// A rung with too few readings is a constant fitted to noise, so the guard is
// a MINIMUM COUNT below which the rung is left alone. Which minimum is itself
// measured rather than picked.
//
// TWO LEVELS, SPLIT ON THE FLOOR OF THE ACTIVE LENGTH. The one-constant form
// is always tried first and a split has to beat it outright, so a rung that
// genuinely wants one level gets one - which is what `t: null` records. Each
// side needs two readings, or the "split" is a level fitted to a single door.
// Fit the two-level form to ONE set of rows. Pulled out of the loop below so
// the same code can fit a rung and fit the pooled fallback.
const fitOne = (g) => {
    const [c, ch] = bestOffset(g);
    let best = { hit: ch, t: null, lo: c, hi: c };

    for (const t of [...new Set(g.map((x) => x.floor))].sort((a, b) => a - b)) {
        const below = g.filter((x) => x.floor < t);
        const above = g.filter((x) => x.floor >= t);

        if (below.length < 2 || above.length < 2) continue;

        const [lo, lh] = bestOffset(below);
        const [hi, hh] = bestOffset(above);

        if (lh + hh > best.hit) best = { hit: lh + hh, t, lo, hi };
    }

    return best;
};

// POOL_FALLBACK=1: A RUNG TOO THIN TO FIT GETS THE GLOBAL ENTRY, NOT NOTHING.
//
// The guard above is a hard choice between two bad options, and the script's
// own split-half shows BOTH losing:
//
//     min  2   thin rungs get their OWN fit   61.2%    noisy
//     min  8   thin rungs get NOTHING         62.5%    biased - ~12 rungs
//     none     nobody gets anything           47.1%      left at the baseline
//
// Own-fit is small-sample variance; nothing is pure bias, and it is a large
// bias here because the band's error is strongly one-sided (143 long against
// 4 short before any correction, median +1.00) and nine of the fitted offsets
// are exactly one inch. So the thin rungs are being left at ~47% when the
// thing they almost certainly want is already known globally.
//
// That is the gap partial pooling fills, and it is the mechanism that gave
// the biggest in-envelope gain of the week. Here it is the simplest form of
// it - complete pooling for the thin, none for the thick - which adds ONE
// global entry rather than a parameter per rung.
//
// NO PER-RUNG SELECTION, DELIBERATELY. The obvious richer version is to let
// each rung choose between its own fit, the global one and nothing. That is
// exactly the trap FORM_BY_CV fell into on 2026-11-17: picking the best of
// several estimates inflates the winner by whatever noise favoured it, and
// the gain evaporates out of sample. This is ONE global rule, scored by the
// same split-half as everything else.
//
// THE VERDICT: IT WINS, AND IT IS SHIPPED. Twenty split-half shuffles with
// the guard PINNED at min 8 for both arms, so nothing is chosen on the test
// half:
//
//     net +69 readings   mean delta 3.45   sd 4.87   se 1.09
//     t = 3.17 on 19 df   15 wins   5 losses
//
// THE GUARD MUST BE PINNED FOR ANY SUCH COMPARISON. Left to scan, the arm
// with more freedom to move `min` is flattered - unpinned, the five-shuffle
// reading was +24 against +32 pinned, so the scan was costing the pooled arm
// its own effect. `MIN=` exists for this.
//
// AND THE TWENTY SHUFFLES ARE NOT TWENTY SAMPLES. They re-partition the SAME
// 603 readings, so this establishes the gain on this data under repeated
// split-half - the standard the two-level form itself was accepted on, and a
// stronger version of it (twenty shuffles against five). It is not evidence
// about a reading nobody has pulled.
//
// WHAT IT BUYS, AND THE HONEST SIZE OF IT: the band goes 67.76% -> 68.42% in
// sample, four readings of 608. Inside 96" is UNCHANGED at 98.52% and 96-120"
// unchanged at 94.49%, which the `inner > 119` gate guarantees and which was
// checked rather than assumed. Golden 725 byte-identical, invariants 20/20.
//
// The global entry comes out {t: 165, lo: 0, hi: 1} - below active length 165
// no correction, above it exactly one inch. The same readable shape as the
// per-rung entries, which is why eight thin rungs inheriting it is a prior
// rather than a guess.
// THE DEFAULT IS THE SHIPPED VALUE, AND THAT IS NOT A STYLE CHOICE.
// `apply-over120.sh` is the documented routine after every pull and it passes
// no environment at all, so a knob defaulting OFF while the installed table
// was fitted with it ON would silently revert itself the next time anybody
// refitted - no code change, no warning. That is the `SHRINK` lesson of
// 2026-11-16. `POOL_FALLBACK=0` is the revert.
const POOL_FALLBACK = process.env.POOL_FALLBACK !== "0";

const fitOffsets = (train, min) => {
    const out = new Map();

    for (const rg of new Set(train.map((x) => x.rung))) {
        const g = train.filter((x) => x.rung === rg);

        if (g.length < min) continue;

        const best = fitOne(g);

        // A rung with enough readings whose answer is "no correction" keeps
        // that answer explicitly, so the fallback cannot overrule a measured
        // zero. Without POOL_FALLBACK there is nothing to overrule it with,
        // so the default behaviour stays byte-identical.
        if (best.lo !== 0 || best.hi !== 0) out.set(rg, best);
        else if (POOL_FALLBACK) out.set(rg, { t: null, lo: 0, hi: 0 });
    }

    if (POOL_FALLBACK) out.set("__fallback__", fitOne(train));

    return out;
};

// The entry a reading is corrected by: its own rung's, else the pooled
// fallback when there is one, else nothing.
const entryFor = (offs, x) => offs.get(x.rung) ?? offs.get("__fallback__");

const offFor = (e, x) => (!e ? 0
    : (e.t === null || x.floor < e.t ? e.lo : e.hi));

console.log(`${rows.length} past-120" readings with the wire right, `
    + `${new Set(rows.map((x) => x.rung)).size} rungs\n`);

// SEED= re-runs the split-half on a different shuffle. 603 readings against
// ~75 parameters is enough freedom for one lucky split, which is why the
// two-level form was accepted on FIVE shuffles and five wins rather than on
// one. Any new comparison here is held to the same standard.
const { rnd } = makeRnd(process.env.SEED || 20261111);
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

// MIN= pins the guard instead of scanning for it. THE SCAN SELECTS ON THE
// TEST HALF - it reports the best of six, which is optimistic for whichever
// arm has more freedom to move - so any A/B comparison of a change to this
// fitter must pin the guard for both arms. Scanning is right when the only
// question is which guard to ship; it is wrong as a yardstick.
const MINS = process.env.MIN ? [Number(process.env.MIN)] : [2, 4, 6, 8, 10, 12];

for (const min of MINS) {
    let tot = 0, kept = 0;

    for (const [train, test] of [[A, B], [B, A]]) {
        const offs = fitOffsets(train, min);

        kept += [...offs.keys()].filter((k) => k !== "__fallback__").length;
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

// THE FALLBACK IS EXPANDED, NOT SHIPPED AS A FALLBACK. The engine looks an
// offset up BY RUNG and has no notion of a default, so under POOL_FALLBACK
// every rung seen in the corpus that has no fit of its own is written out
// carrying the global entry explicitly. The table stays a plain lookup and
// the engine needs no change. A rung the corpus has never seen still gets
// nothing at runtime, exactly as today.
if (POOL_FALLBACK) {
    const fb = final.get("__fallback__");

    final.delete("__fallback__");

    for (const rg of new Set(rows.map((x) => x.rung))) {
        if (!final.has(rg)) final.set(rg, fb);
    }

    console.log(`POOL_FALLBACK: the global entry {t:${fb.t}, lo:${fb.lo}, `
        + `hi:${fb.hi}} is written out to every rung with no fit of its own\n`);
}

console.log(`SHIPPED TABLE: ${final.size} rungs carry an offset `
    + `(the rest are left alone)\n`);

const js = "{ " + [...final].sort()
    .map(([k, v]) => `"${k}": {t:${v.t}, lo:${v.lo}, hi:${v.hi}}`).join(", ") + " }";

console.log(js);
writeFileSync(join(HERE, "over120-offsets.json"),
    JSON.stringify(Object.fromEntries([...final]
        .map(([k, v]) => [k, { t: v.t, lo: v.lo, hi: v.hi }])), null, 1) + "\n");
console.log(`\nwritten to dev/over120-offsets.json`);
console.log(`in-sample with this table: `
    + `${(score(rows, final) / rows.length * 100).toFixed(1)}% `
    + `(optimistic by construction - quote the split-half figure)`);
