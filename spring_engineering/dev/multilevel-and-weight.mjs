// THE TWO SLICES NOTHING HAS EVER MEASURED.
//
//   node dev/multilevel-and-weight.mjs
//
// 1. MULTI-LEVEL GROUPS. dev/miss-margin.mjs showed the in-envelope failures
//    hug their threshold and STRADDLE it, so no placement of the line wins -
//    but it deliberately covered only PLAIN TWO-LEVEL groups and skipped every
//    group carrying `cuts` (K parallel thresholds) or `mid` (three levels).
//    That is the largest slice of in-envelope failures never looked at
//    individually. The same question has to be asked of them: near the
//    boundary, or far from it?
//
// 2. DUPLEX WEIGHT. `dev/envelope.mjs` scores a reading EXACT on wire and
//    length. Weight is a third output the reference reports and nothing here
//    has ever scored it for duplex. A systematic weight error would be
//    invisible to every tool in this directory - and weight is what a spring
//    is PRICED from, so it is money rather than a specification.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const multi = [];
const weights = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const step = c.duplexStep;

    if (!step) continue;

    const rung = `${step.outerWire}/${step.innerWire}`;

    if (rung !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;                           // wire miss: a different spring
    }

    if (Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength) > 96) {
        continue;                           // in-envelope only
    }

    // ---------------------------------------------------- weight
    if (r.expect.duplexInnerWeight !== undefined
        && r.expect.duplexOuterWeight !== undefined) {
        const oi = c.duplexInnerWeight, oo = c.duplexOuterWeight;

        if (oi > 0 && oo > 0) {
            weights.push({
                rung,
                inner: oi / r.expect.duplexInnerWeight,
                outer: oo / r.expect.duplexOuterWeight,
                lenOk: c.duplexInnerLength === r.expect.duplexInnerLength
                    && c.duplexOuterLength === r.expect.duplexOuterLength,
            });
        }
    }

    // ---------------------------------------------------- multi-level groups
    const springs = c.duplexSpringCount;
    const split = step.splitByCount && step.splitByCount[springs];
    const act = c.duplexActiveLength;
    const whole = Math.floor(act);
    const line = split
        ? (whole >= split.from ? split.above : split.below)
        : step.lineByCount && step.lineByCount[springs];

    if (!line) continue;
    if (!line.cuts && line.mid === undefined) continue;   // handled elsewhere

    const frac = act - whole;
    // EVERY threshold this group decides on, in frac coordinates.
    const thresholds = [line.a + line.b * whole];

    if (line.cuts) {
        for (const cut of line.cuts) thresholds.push(cut + line.b * whole);
    } else {
        thresholds.push(line.a2 + (line.b2 ?? line.b) * whole);
    }

    const margin = thresholds
        .map((t) => frac - t)
        .reduce((a, b) => (Math.abs(b) < Math.abs(a) ? b : a));

    multi.push({
        group: `${rung} ${springs}spr`,
        levels: line.cuts ? line.levels.length : 3,
        margin,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

// =========================================================== 1. multi-level
const bad = multi.filter((x) => !x.ok);

console.log(`1. MULTI-LEVEL GROUPS (three or more bonus levels)\n`);
console.log(`   ${multi.length} in-envelope readings, ${bad.length} failing\n`);
console.log("   distance to the NEAREST threshold that decides the group\n");
console.log("   |margin|        failures    all readings");

for (const [lo, hi] of [[0, .01], [.01, .025], [.025, .05], [.05, .1],
    [.1, .2], [.2, .4], [.4, 1e9]]) {
    const f = bad.filter((x) => Math.abs(x.margin) > lo && Math.abs(x.margin) <= hi);
    const a = multi.filter((x) => Math.abs(x.margin) > lo && Math.abs(x.margin) <= hi);

    if (!a.length) continue;

    console.log(`   ${`${lo}-${hi === 1e9 ? "+" : hi}`.padEnd(14)}`
        + `${String(f.length).padStart(6)} `
        + `${(bad.length ? f.length / bad.length * 100 : 0).toFixed(1).padStart(6)}%`
        + `${String(a.length).padStart(10)} `
        + `${(a.length / multi.length * 100).toFixed(1).padStart(6)}%`);
}

const med = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
};

if (bad.length) {
    console.log(`\n   median |margin|   failing `
        + `${med(bad.map((x) => Math.abs(x.margin))).toFixed(4)}`
        + `   all ${med(multi.map((x) => Math.abs(x.margin))).toFixed(4)}`);
}

console.log("\n   SAME SHAPE AS THE TWO-LEVEL GROUPS means these failures are");
console.log("   threshold straddlers too and the whole in-envelope residual is");
console.log("   one mechanism. A FLAT spread would mean these are different and");
console.log("   worth their own attack.");

// =============================================================== 2. weight
console.log(`\n\n2. DUPLEX WEIGHT - never scored before\n`);
console.log(`   ${weights.length} readings with the wire right\n`);

const report = (label, xs) => {
    if (xs.length < 10) return;

    const s = xs.slice().sort((a, b) => a - b);
    const p = (f) => s[Math.min(s.length - 1, Math.floor(s.length * f))];
    const exact = xs.filter((x) => Math.abs(x - 1) < 0.005).length;

    console.log(`   ${label.padEnd(22)}p10 ${p(.1).toFixed(4)}  `
        + `median ${p(.5).toFixed(4)}  p90 ${p(.9).toFixed(4)}   `
        + `within 0.5%: ${(exact / xs.length * 100).toFixed(1)}%`);
};

report("inner spring", weights.map((x) => x.inner));
report("outer spring", weights.map((x) => x.outer));
console.log("");
report("inner, length right", weights.filter((x) => x.lenOk).map((x) => x.inner));
report("outer, length right", weights.filter((x) => x.lenOk).map((x) => x.outer));

console.log("\n   WEIGHT FOLLOWS LENGTH - it is wire cross-section x length x");
console.log("   density - so where the length is right the weight should be");
console.log("   too. A gap between those two pairs of lines would mean the");
console.log("   weight formula itself is off, which would be a PRICING fault");
console.log("   rather than a specification one.");
