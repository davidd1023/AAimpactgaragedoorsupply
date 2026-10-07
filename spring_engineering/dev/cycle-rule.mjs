// WHEN DOES THE REFERENCE COMPLAIN THAT A SPRING IS SHORT OF ITS TARGET?
//
//   node dev/cycle-rule.mjs
//
// This module raises duplex-cycles-low on 390 readings the reference passes
// cleanly, against 173 where the two agree - crying wolf two to one. The code
// around that warning says the groups cannot be separated by any threshold,
// and that is true of OUR computed cycle count. It is not true of the
// reference's own: measured against the figure the reference itself reports,
// the rule separates almost perfectly, and it is not "below target" at all.
// The reference tolerates a shortfall.
//
// THE ANSWER IS AN ABSOLUTE FLOOR AT 10,000, not a fraction of the target,
// and the module now uses it: false alarms went from 335 to 4 with the same
// 173 agreements and the same 5 misses. The rule was hard to see because every
// warned reading in the corpus has a target of 10,000, so a fraction of the
// target fits the data exactly as well - and because the earlier search for it
// scanned thresholds from 0.70 to 1.05 OF THE TARGET, a family that cannot
// contain a constant. A search over the wrong family reports "no threshold
// works" however much data it is given.
//
// What gives it away, below: every warned reading reports exactly 9,000 cycles
// across weights from 459 lb to 1,949 lb and eleven rungs, and a door that
// misses a HIGH target is passed in silence.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { stateFromReading, isModelledDuplex, REF_RADIUS } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const rows = [];
const seen = new Set();

for (const f of readdirSync(HERE).filter((x) => /\.json$/.test(x))) {
    let data;

    try {
        data = JSON.parse(readFileSync(join(HERE, f), "utf8"));
    } catch {
        continue;
    }

    const list = Array.isArray(data) ? data : (data.readings ?? []);

    if (!Array.isArray(list)) continue;

    for (const r of list) {
        const i = r?.input;

        if (!i || r.error || !i.cycles || !isModelledDuplex(i) || !i.heightInches) continue;
        if (!(Number(i.radius) in REF_RADIUS)) continue;

        // A reported count of zero is a failed calculation, not a short
        // spring - "Unable to get a Wire Size", "Invalid data input". Those
        // were the only readings any candidate rule got wrong, and they are
        // not what the rule is about.
        if (!r.data?.cycles) continue;

        const key = JSON.stringify([i.drum, i.springs, i.radius, i.lift, i.hiLift,
                                    i.heightInches, i.weight, i.cycles, i.widthInches]);

        if (seen.has(key)) continue;

        seen.add(key);

        rows.push({
            ref: r.data.cycles, target: Number(i.cycles),
            low: (r.messages ?? []).some((m) => /cycle/i.test(m) && !/exceed/i.test(m)),
            input: i, data: r.data,
        });
    }
}

console.log(`${rows.length} distinct readings with a target and a cycle count\n`);

const RULES = {
    "reported < target":            (r) => r.ref < r.target,
    "reported <= 0.95 * target":    (r) => r.ref <= 0.95 * r.target,
    "reported <= 0.90 * target":    (r) => r.ref <= 0.90 * r.target,
    "reported <= 0.85 * target":    (r) => r.ref <= 0.85 * r.target,
    "reported < 10,000 (absolute)": (r) => r.ref < 10000,
};

console.log("THE REFERENCE'S OWN RULE, against the count it reports itself:");
console.log("  rule                           false alarms   missed");

for (const [name, f] of Object.entries(RULES)) {
    console.log(`  ${name.padEnd(30)} ${String(rows.filter((r) => f(r) && !r.low).length).padStart(12)}`
        + `   ${String(rows.filter((r) => !f(r) && r.low).length).padStart(6)}`);
}

// HOW WELL THIS IS REALLY PINNED. It looks like a solved rule and it is not:
// the warned readings are all one target at one ratio, so the data brackets
// the tolerance and no more.
const warned = rows.filter((r) => r.low);
const ratios = [...new Set(warned.map((r) => (r.ref / r.target).toFixed(4)))].sort();
const targets = [...new Set(warned.map((r) => r.target))].sort((a, b) => a - b);

console.log(`\n  ${warned.length} warned readings, at target(s) ${targets.join(", ")}`);
console.log(`  and at reported/target of ${ratios.join(", ")} only.`);

const quietBelow = rows.filter((r) => !r.low && r.ref / r.target < 0.98)
    .map((r) => r.ref / r.target).sort((a, b) => a - b);

if (quietBelow.length) {
    console.log(`  the lowest ratio it stays QUIET at is ${quietBelow[0].toFixed(4)}.`);
    console.log("");
    console.log("  Read as a tolerance that brackets it to (0.9000, 0.9333] and no");
    console.log("  tighter. Read as a floor there is nothing to bracket: one target and");
    console.log("  one ratio is exactly what a constant 10,000 produces, because 9,000 is");
    console.log("  the only bucket beneath it and only a 10,000 target can reach it.");
}

// The reported value on every warned reading, which is the tell.
const vals = [...new Set(warned.map((r) => r.ref))].sort((a, b) => a - b);
const weights = warned.map((r) => r.input.weight).filter((w) => typeof w === "number");

console.log(`\n  reported cycle counts across all ${warned.length} warned readings: `
    + `${vals.join(", ")}`);

if (weights.length) {
    console.log(`  at door weights from ${Math.min(...weights)} lb to ${Math.max(...weights)} lb.`);
    console.log("  One reported value over that spread is a floor, not a tolerance.");
}

// THE HALF THAT ACTUALLY BLOCKS THE FIX.
console.log("\nOUR OWN COUNT, where we picked the reference's pairing:");

const ours = [];

for (const r of rows) {
    const c = make(mod, stateFromReading(r.input));
    const s = c.duplexStep;

    if (!s || s.innerWire !== r.data.innerSpring?.wireSize
        || s.outerWire !== r.data.outerSpring?.wireSize) continue;

    const exact = c.duplexCyclesExact;

    if (typeof exact !== "number" || !isFinite(exact) || exact <= 0) continue;

    ours.push({ ...r, ours: exact });
}

const q = (xs, p) => xs.slice().sort((a, b) => a - b)[Math.floor(p * (xs.length - 1))];
const rel = ours.map((r) => r.ours / r.ref - 1);

console.log(`  ${ours.length} readings   median ${(100 * q(rel, 0.5)).toFixed(2)}%`
    + `   p95 ${(100 * q(rel, 0.95)).toFixed(2)}%   p99 ${(100 * q(rel, 0.99)).toFixed(2)}%`);

console.log("\n  the error shrinks as the target grows, which is the signature of the");
console.log("  reference's own 1000-cycle quantisation rather than of our model:");
console.log("  target      n   median    p95");

const byT = new Map();

for (const r of ours) {
    if (!byT.has(r.target)) byT.set(r.target, []);
    byT.get(r.target).push(r.ours / r.ref - 1);
}

for (const [t, v] of [...byT].sort((a, b) => a[0] - b[0])) {
    if (v.length < 20) continue;

    console.log(`  ${String(t).padStart(7)} ${String(v.length).padStart(6)}  `
        + `${(100 * q(v, 0.5)).toFixed(2).padStart(6)}%  ${(100 * q(v, 0.95)).toFixed(2).padStart(6)}%`);
}

// FLOOR OR ROUND - unresolved, and this is why.
const resid = ours.map((r) => r.ours - r.ref).filter((d) => Math.abs(d) < 1500);
const inBand = resid.filter((d) => d >= 0 && d < 1000).length;

console.log(`\n  of ${resid.length} residuals inside 1500 cycles, ${inBand}`
    + ` (${(100 * inBand / resid.length).toFixed(0)}%) fall in [0, 1000).`);
console.log("  That is what flooring to 1000 looks like - but it is also what rounding");
console.log("  to 1000 looks like if our own count runs ~500 high, and nothing here can");
console.log("  tell those apart. Settling it needs a sweep in which the exact cycle life");
console.log("  is known independently of our own cycle law.");
