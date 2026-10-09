// WHERE in the chain does a Duplex length miss come from?
//
//   node dev/link-check.mjs dev/eval-validation-seed61006.json [...]
//
// The reference reports its own intermediates on every reading -
// `totalInchPoundPerTurn`, `turnsOnSprings` and `multiplier` - so our chain can
// be checked link by link instead of only at the final length. Pass external
// files; the corpus does not carry the reference's intermediates.
//
// WHY THIS IS THE FIRST THING TO RUN on any new length idea. It answers "is the
// error even where I think it is" for the cost of one query, and the answer has
// been counter-intuitive every time it was asked:
//
//   TIPPT      97.6% on the readings we get RIGHT, 100% on the misses
//   turns      99.1% right, 100% on the misses
//   multiplier 93.4% right, 100% on the misses
//
// Upstream is PERFECT on every miss and imperfect on the exact ones. So a
// repair to the multiplier surface or the TIPPT rounding cannot move the length
// figure, however wrong it looks on its own - and the whole error lives in S,
// the per-rung stiffness. Two sessions were spent on upstream surfaces before
// anyone measured this.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { stateFromReading, isClean, isModelledDuplex } from "./ref-state.mjs";

const mod = await load();
const files = process.argv.slice(2);

if (!files.length) {
    console.error("usage: node dev/link-check.mjs <external.json> [...]");
    process.exit(1);
}

const rows = [];

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

        if (!d || r.error || !isModelledDuplex(i) || !isClean(r)) continue;

        const inn = d.innerSpring, out = d.outerSpring;

        if (!inn?.springLength || !out?.springLength) continue;
        if (d.totalInchPoundPerTurn == null || d.turnsOnSprings == null) continue;

        const c = make(mod, stateFromReading(i));
        const s = c.duplexStep;

        if (!s) continue;

        // The wire must agree, or this is a wire question wearing a length
        // question's clothes.
        if (`${s.outerWire}/${s.innerWire}`
            !== `${parseFloat(out.wireSize)}/${parseFloat(inn.wireSize)}`) continue;

        const springs = i.springs ?? 2;
        const ourT = c.tipptRounded ?? c.tippt ?? NaN;

        rows.push({
            miss: c.duplexInnerLength !== inn.springLength,
            dIn: c.duplexInnerLength - inn.springLength,
            tipptOk: Math.abs(ourT - d.totalInchPoundPerTurn) < 5e-2,
            turnsOk: Math.abs((c.turns ?? NaN) - d.turnsOnSprings) < 5e-2,
            multOk: Math.abs((c.multiplierExact ?? NaN) - d.multiplier) < 2e-5,
            // S as the reference implies it, against S as we use it. Both from
            // the SHOWN TIPPT, because that is what the reference computes from.
            refS: (inn.springLength * d.totalInchPoundPerTurn) / springs,
            ourS: (c.duplexInnerLength * d.totalInchPoundPerTurn) / springs,
        });
    }
}

const ex = rows.filter((r) => !r.miss), ms = rows.filter((r) => r.miss);
const rate = (a, k) => (a.length
    ? `${(100 * a.filter((x) => x[k]).length / a.length).toFixed(1)}%` : "   -  ");

console.log(`clean modelled Duplex, wire agreeing: ${rows.length}`
    + `  (exact ${ex.length}, miss ${ms.length})\n`);
console.log("                      exact     miss");

for (const [label, k] of [["TIPPT matches", "tipptOk"],
    ["turns matches", "turnsOk"], ["multiplier matches", "multOk"]]) {
    console.log(`  ${label.padEnd(20)}${rate(ex, k).padStart(7)}  ${rate(ms, k).padStart(7)}`);
}

if (!ms.length) {
    process.exit(0);
}

const ratios = ms.map((m) => m.ourS / m.refS).sort((a, b) => a - b);

console.log(`\nS needed vs S used, over the misses:`);
console.log(`  min ${ratios[0].toFixed(5)}   median ${ratios[Math.floor(ratios.length / 2)].toFixed(5)}`
    + `   max ${ratios[ratios.length - 1].toFixed(5)}`);
console.log("\nthe misses:");
console.log("    dIn      refS       ourS    S ratio   upstream all exact?");

for (const m of ms) {
    console.log(`  ${(m.dIn > 0 ? "+" : "") + m.dIn.toFixed(2).padStart(5)}`
        + `  ${m.refS.toFixed(1).padStart(9)}  ${m.ourS.toFixed(1).padStart(9)}`
        + `   ${(m.ourS / m.refS).toFixed(5)}   `
        + `${m.tipptOk && m.turnsOk && m.multOk ? "yes" : "NO"}`);
}
