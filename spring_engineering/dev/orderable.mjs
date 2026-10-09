// Accuracy on doors a customer can actually ORDER, split from doors the
// reference refuses to build.
//
//   node dev/orderable.mjs dev/eval-validation-seed61006.json [...]
//
// WHY THIS SPLIT AND NOT clean/flagged. dev/clean-cases.mjs reports flagged
// readings at about 79% length and that reads like a weakness in half the
// population. It is not. Nearly every flagged reading is the reference
// REFUSING: the spring is over 120", the assembly will not fit the widest
// door, the wire is past the inside diameter's maximum, the drum is
// overloaded. Those doors cannot be bought at any accuracy, so the model's
// answer for them is not a quote - it is the input to a warning.
//
// What matters is the complement: readings the reference WARNS about and will
// still build - "only spring lengths between 0 and 96 are recommended" and the
// short-cycle-life notes. A customer can order those over the warning, and
// they are long springs, so they are the hard ones.
//
// Measured on the two never-tuned draws: warned-but-buildable comes out at
// 100% of 85, against 98.0% for the clean ones. The hard-looking half of the
// flagged bucket was never a weakness; it was refusals.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { stateFromReading, isModelledDuplex } from "./ref-state.mjs";

const mod = await load();

// A complaint that means "I will not build this", as opposed to one that means
// "I will build this but look at it first".
const REFUSALS = [
    /between 0 and 120/i,       // over the longest spring it supports
    /too long for a/i,          // assembly longer than the door is wide
    /Wire size exceeds/i,       // past the inside diameter's maximum
    /does not meet/i,           // under its minimum
    /Unable to get a Wire Size/i,
    /heavier than this drum/i,
    /over max MIP/i,
];

const files = process.argv.slice(2);

if (!files.length) {
    console.error("usage: node dev/orderable.mjs <external.json> [...]");
    process.exit(1);
}

const buckets = new Map();
const order = ["clean", "warned but buildable", "ORDERABLE (both)", "refused"];

for (const k of order) {
    buckets.set(k, { n: 0, wire: 0, exact: 0, in1: 0 });
}

function tally(k, wireOk, exact, in1) {
    const b = buckets.get(k);

    b.n += 1;

    if (wireOk) {
        b.wire += 1;
        b.exact += exact ? 1 : 0;
        b.in1 += in1 ? 1 : 0;
    }
}

for (const f of files) {
    let data;

    try {
        data = JSON.parse(readFileSync(f, "utf8"));
    } catch {
        console.error(`skipping ${f} - unreadable`);
        continue;
    }

    for (const r of data) {
        const i = r.input, d = r.data;

        if (!d || r.error || !isModelledDuplex(i)) continue;

        const inn = d.innerSpring, out = d.outerSpring;

        if (!inn?.springLength || !out?.wireSize) continue;

        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(String(m)));
        const refused = msgs.some((m) => REFUSALS.some((re) => re.test(String(m))));

        let c, s;

        try { c = make(mod, stateFromReading(i)); s = c.duplexStep; } catch { continue; }

        if (!s) continue;

        const wireOk = `${s.outerWire}/${s.innerWire}`
            === `${parseFloat(out.wireSize)}/${parseFloat(inn.wireSize)}`;
        const dLen = c.duplexInnerLength - inn.springLength;
        const exact = dLen === 0;
        const in1 = Math.abs(dLen) <= 1;

        if (refused) {
            tally("refused", wireOk, exact, in1);
        } else {
            tally(msgs.length ? "warned but buildable" : "clean", wireOk, exact, in1);
            tally("ORDERABLE (both)", wireOk, exact, in1);
        }
    }
}

const pc = (x, d) => (d ? `${(100 * x / d).toFixed(1)}%` : "  -  ");

console.log('class                       n    wire   length exact   within 1"');

for (const k of order) {
    const b = buckets.get(k);

    if (!b.n) continue;

    console.log(`${k.padEnd(26)}${String(b.n).padStart(4)}  ${pc(b.wire, b.n).padStart(6)}`
        + `  ${pc(b.exact, b.wire).padStart(12)}  ${pc(b.in1, b.wire).padStart(10)}`);
}

console.log("\nlength percentages are of the readings whose WIRE agrees, so a wire");
console.log("miss is not counted twice. A refused door cannot be ordered at all.");
