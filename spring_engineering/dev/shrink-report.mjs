// COMPARE TWO HOLDOUT RUNS READING BY READING, NOT TOTAL BY TOTAL.
//
//   node dev/shrink-report.mjs /home/odoo/logs/shrink-0.rows /home/odoo/logs/shrink-25.rows
//
// WHY PAIRED. Two five-fold runs differ by whatever the fitter happened to do
// on each fold, and the fold-to-fold standard deviation here is 10.5 readings
// - so comparing TOTALS cannot resolve anything smaller than about +-21. That
// is not a hypothetical: the LINE_SLACK screen of 2026-11-12 read a +10 as
// promising and four confirming folds put the interval at -12.5 to +21.0.
//
// Pairing removes all of it. Every reading is scored once per configuration,
// out of sample, under the same fold assignment - so the readings that did
// NOT change contribute nothing to the comparison, and the ones that did are
// counted exactly. McNemar's test on the discordant pairs is then the whole
// answer, and it needs no assumption about the spread of fold totals.
//
// READ THE DISCORDANT COUNTS, NOT THE TOTALS. b and c below are the only
// numbers carrying information; a difference of +8 built from 9 fixed and 1
// broken is a real effect, and the same +8 from 108 fixed and 100 broken is
// a coin toss with a long run.
import { readFileSync } from "node:fs";

const files = process.argv.slice(2);

if (files.length !== 2) {
    console.error("usage: node dev/shrink-report.mjs <a.rows> <b.rows>");
    process.exit(1);
}

function rows(path) {
    const m = new Map();

    for (const line of readFileSync(path, "utf8").split("\n")) {
        if (!line.startsWith("ROW\t")) continue;

        const [, id, ok] = line.split("\t");

        // A reading scored twice would mean the folds overlap - that is a
        // broken run, not something to average away.
        if (m.has(id)) {
            console.error(`  ${path}: ${id} scored twice - folds overlap, stopping`);
            process.exit(1);
        }

        m.set(id, ok === "1");
    }

    return m;
}

const A = rows(files[0]);
const B = rows(files[1]);
const shared = [...A.keys()].filter((k) => B.has(k));

let a = 0, b = 0, c = 0, d = 0;

for (const k of shared) {
    const x = A.get(k), y = B.get(k);

    if (x && y) a++;
    else if (x && !y) b++;          // the first got it, the second lost it
    else if (!x && y) c++;          // the second fixed it
    else d++;
}

const name = (p) => p.split("/").pop().replace(/\.rows$/, "");

console.log("=".repeat(70));
console.log(`PAIRED HOLDOUT: ${name(files[0])}  vs  ${name(files[1])}`);
console.log("=".repeat(70));
console.log(`  readings scored by both : ${shared.length}`);
console.log(`  ${name(files[0])} correct : ${a + b}`);
console.log(`  ${name(files[1])} correct : ${a + c}`);
console.log(`  difference              : ${c - b >= 0 ? "+" : ""}${c - b}`);
console.log();
console.log(`  both right  ${a}`);
console.log(`  both wrong  ${d}`);
console.log(`  FIXED by the second  ${c}`);
console.log(`  BROKEN by the second ${b}`);

const disc = b + c;

if (!disc) {
    console.log("\n  NOTHING CHANGED. The two fits are identical on every"
        + " reading scored.");
    process.exit(0);
}

// McNemar, exact two-sided binomial on the discordant pairs. With b + c this
// small a chi-square approximation is not worth trusting.
function logC(n, k) {
    let s = 0;

    for (let i = 1; i <= k; i++) s += Math.log(n - k + i) - Math.log(i);

    return s;
}

let p = 0;
const target = Math.min(b, c);

for (let i = 0; i <= target; i++) {
    p += Math.exp(logC(disc, i) - disc * Math.LN2);
}

p = Math.min(1, 2 * p);

console.log(`\n  discordant pairs ${disc}`);
console.log(`  McNemar exact two-sided p = ${p.toFixed(4)}`);
console.log(`  ${p < 0.05
    ? `  ** SIGNIFICANT at 0.05 - the ${c > b ? "second" : "first"} is better **`
    : "  not significant - this is within what chance gives"}`);
