// HOW FAR IS EACH IN-ENVELOPE FAILURE FROM THE THRESHOLD THAT DECIDED IT?
//
//   node dev/miss-margin.mjs
//
// THE FIRST TOOL IN THIS PROJECT TO LOOK AT AN INDIVIDUAL IN-ENVELOPE MISS.
// Everything before it measured aggregates - group shapes, knob sweeps, form
// ladders, fold scores - and the two things that ever actually worked here
// (the twelfth form past 120", and both "bugs" that turned out not to exist)
// came from printing one concrete case instead of reasoning about a summary.
//
// WHAT IT COMPUTES. A two-level group picks its bonus as
//
//     bonus = frac > (a + b * floor) ? hi : lo
//
// so every reading has a signed distance from that boundary:
//
//     margin = frac - (a + b * floor)
//
// and a FAILURE is a reading the boundary put on the wrong side.
//
// THE TWO OUTCOMES POINT OPPOSITE WAYS, which is what makes it worth running:
//
//   - failures HUG the boundary (|margin| small, and small relative to the
//     spread of the group's own readings) -> the line is very slightly
//     misplaced. That is a FIT problem and more care in placing one number
//     per group could win them.
//
//   - failures sit FAR from the boundary -> they wanted the other level
//     outright, and no placement of a single straight threshold catches them
//     without losing the readings now on that side. That is a FORM problem
//     and this shape cannot hold them, whatever the gates are set to.
//
// It needs no requests and no database.
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

    const rung = `${step.outerWire}/${step.innerWire}`;

    // A wire miss is a different spring; its length is not comparable.
    if (rung !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    // IN-ENVELOPE ONLY - past 120" has its own table and its own diagnostics.
    if (Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength) > 96) {
        continue;
    }

    const springs = c.duplexSpringCount;
    const split = step.splitByCount && step.splitByCount[springs];
    const act = c.duplexActiveLength;
    const whole = Math.floor(act);
    const line = split
        ? (whole >= split.from ? split.above : split.below)
        : step.lineByCount && step.lineByCount[springs];

    // ONLY THE PLAIN TWO-LEVEL SHAPE. A group with `cuts` or `mid` decides on
    // more than one boundary and a single margin would not describe it.
    if (!line || line.cuts || line.mid !== undefined) continue;

    rows.push({
        group: `${rung} ${springs}spr`,
        whole,
        frac: act - whole,
        margin: (act - whole) - (line.a + line.b * whole),
        gave: c.duplexInnerLength - whole,
        want: r.expect.duplexInnerLength - whole,
        lo: line.lo, hi: line.hi,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

const bad = rows.filter((x) => !x.ok);

console.log(`${rows.length} in-envelope readings in plain TWO-LEVEL groups, `
    + `${bad.length} failing\n`);

// ------------------------------------------------- 1. the decisive histogram
console.log("1. HOW FAR FROM THE BOUNDARY?  |margin| = |frac - (a + b*floor)|\n");
console.log("  |margin|        failures    all readings");

const bands = [[0, 0.01], [0.01, 0.025], [0.025, 0.05], [0.05, 0.1],
    [0.1, 0.2], [0.2, 0.4], [0.4, 1e9]];

for (const [lo, hi] of bands) {
    const f = bad.filter((x) => Math.abs(x.margin) > lo && Math.abs(x.margin) <= hi);
    const a = rows.filter((x) => Math.abs(x.margin) > lo && Math.abs(x.margin) <= hi);

    console.log(`  ${`${lo}-${hi === 1e9 ? "+" : hi}`.padEnd(14)}`
        + `${String(f.length).padStart(6)} `
        + `${(f.length / bad.length * 100).toFixed(1).padStart(6)}%`
        + `${String(a.length).padStart(10)} `
        + `${(a.length / rows.length * 100).toFixed(1).padStart(6)}%`);
}

const med = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
};

console.log(`\n  median |margin|   failing ${med(bad.map((x) => Math.abs(x.margin))).toFixed(4)}`
    + `   all ${med(rows.map((x) => Math.abs(x.margin))).toFixed(4)}`);
console.log("\n  FAILURES CONCENTRATED NEAR ZERO means the boundary is very");
console.log("  slightly misplaced - a FIT problem, winnable by placing one");
console.log("  number per group better. FAILURES SPREAD OUT means they wanted");
console.log("  the other level outright and this SHAPE cannot hold them.");

// ------------------------------------------------- 2. which way they fail
console.log("\n2. WHICH SIDE?\n");

const wrongHigh = bad.filter((x) => x.margin > 0 && x.want < x.gave).length;
const wrongLow = bad.filter((x) => x.margin <= 0 && x.want > x.gave).length;

console.log(`  we said HI, reference wanted LO:  ${wrongHigh}`);
console.log(`  we said LO, reference wanted HI:  ${wrongLow}`);
console.log(`  neither level was right:          `
    + `${bad.length - wrongHigh - wrongLow}   <- the form cannot hold these`);

// --------------------------------------- 3. could moving the line win them?
console.log("\n3. COULD A BETTER-PLACED LINE WIN THEM, group by group?\n");
console.log("  group                      n  fails  best possible   gain");

const byGroup = new Map();

for (const x of rows) {
    if (!byGroup.has(x.group)) byGroup.set(x.group, []);

    byGroup.get(x.group).push(x);
}

let gain = 0, gfails = 0;

for (const [g, xs] of [...byGroup].sort((a, b) =>
    b[1].filter((x) => !x.ok).length - a[1].filter((x) => !x.ok).length)) {
    const f = xs.filter((x) => !x.ok).length;

    if (!f) continue;

    gfails += f;

    // Slide the boundary over every observed margin and take the best it can
    // do. IN-SAMPLE and therefore the CEILING - if even this cannot recover
    // them, no fit of this shape can.
    let best = xs.length - f;

    for (const cand of xs.map((x) => x.margin)) {
        const hit = xs.filter((x) => {
            const lvl = x.margin > cand ? x.hi : x.lo;
            return lvl === x.want;
        }).length;

        if (hit > best) best = hit;
    }

    const g2 = best - (xs.length - f);

    gain += g2;
    console.log(`  ${g.padEnd(24)}${String(xs.length).padStart(4)}`
        + `${String(f).padStart(6)}${String(best).padStart(14)} / ${xs.length}`
        + `${g2 > 0 ? `   +${g2}` : "   none"}`);
}

console.log(`\n  AT BEST, sliding every boundary in-sample recovers ${gain} `
    + `of ${gfails} failures.`);
console.log("  In-sample is the CEILING and would not survive cross-validation,");
console.log("  so a small number here means the shape is spent and a large one");
console.log("  means the PLACEMENT is what is wrong.");
