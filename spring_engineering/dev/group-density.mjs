// WOULD CONCENTRATED PULLS AT THE PROBLEM AREAS HELP? THE DECISIVE TEST.
//
//   node dev/group-density.mjs
//
// THE QUESTION HAS BEEN ASKED THREE TIMES and answered properly once. Batch
// S2 filled the two worst RUNGS to the same target that fixed the owner's own
// rung - 124 -> 320 readings on `0.3938/0.3195` - and its failure count moved
// by ZERO. That is strong, but it tested the wrong unit.
//
// THE FITTER'S UNIT IS (rung, spring count), not the rung. `lineByCount`
// holds a separate line per spring count, so a rung can hold 320 readings
// while the 2-spring group inside it holds 30. The rung-targeting allocator
// cannot see that, so "the rung is full" has never meant "the group that is
// failing is full".
//
// SO THIS ASKS THE ONE QUESTION THAT SETTLES IT: does the failure rate FALL
// as a group fills? Two outcomes, and they point opposite ways:
//
//   - rate declines with size  -> data helps, and the curve says how much
//                                 would buy what, per group
//   - rate is FLAT             -> fit-bound. No concentration of readings
//                                 helps, because the groups that fail are
//                                 not the groups that are thin.
//
// AND A SECOND CHECK THAT IS NEARLY CONCLUSIVE ON ITS OWN. A failing reading
// is IN THE CORPUS - the fitter has already been shown the reference's answer
// for those exact inputs and still gets it wrong. Buying another reading at
// that same key buys a copy of something already held. This counts how many
// readings each failure's own key already carries; if that is routinely 1 or
// more, concentrated pulls are definitionally useless there and the argument
// needs no curve at all.
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

    const refMax = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);

    // IN-ENVELOPE ONLY. Past 120" the reference disclaims its own answer, so
    // those failures are not evidence about whether data helps - and they now
    // carry the gated correction besides.
    if (refMax > 120) continue;

    const rung = `${step.outerWire}/${step.innerWire}`;
    const wireOk = rung
        === `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
    const act = c.duplexActiveLength;
    const floor = Math.floor(act);

    rows.push({
        rung,
        springs: c.duplexSpringCount,
        group: `${rung}|${c.duplexSpringCount}`,
        // the bonus key - what the fitter actually looks a reading up by
        key: `${rung}|${c.duplexSpringCount}|${floor}|${(act - floor).toFixed(2)}`,
        wireOk,
        ok: wireOk
            && c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

console.log(`${rows.length} in-envelope readings, `
    + `${rows.filter((x) => !x.ok).length} failing\n`);

// ------------------------------------------------- 1. the curve that decides
const byGroup = new Map();

for (const x of rows) {
    if (!byGroup.has(x.group)) byGroup.set(x.group, { n: 0, bad: 0 });

    const g = byGroup.get(x.group);

    g.n++;
    if (!x.ok) g.bad++;
}

console.log("1. DOES THE FAILURE RATE FALL AS A (rung, spring count) GROUP FILLS?\n");
console.log("  group size    groups   readings   failures   failure rate");

const bands = [[1, 9], [10, 24], [25, 49], [50, 99], [100, 249], [250, 1e9]];

for (const [lo, hi] of bands) {
    const gs = [...byGroup.values()].filter((g) => g.n >= lo && g.n <= hi);

    if (!gs.length) continue;

    const n = gs.reduce((a, g) => a + g.n, 0);
    const bad = gs.reduce((a, g) => a + g.bad, 0);

    console.log(`  ${`${lo}-${hi === 1e9 ? "+" : hi}`.padEnd(12)}`
        + `${String(gs.length).padStart(6)}   ${String(n).padStart(8)}   `
        + `${String(bad).padStart(8)}   ${(bad / n * 100).toFixed(2).padStart(6)}%`);
}

console.log("\n  A FLAT column on the right means fit-bound: the groups that fail");
console.log("  are not the groups that are thin, so no concentration of readings");
console.log("  reaches them. A DECLINING column means data still pays.");

// ------------------------------------------------- 2. is the answer already held
const byKey = new Map();

for (const x of rows) byKey.set(x.key, (byKey.get(x.key) ?? 0) + 1);

const fails = rows.filter((x) => !x.ok);
const keyCounts = fails.map((x) => byKey.get(x.key));
const hist = {};

for (const c of keyCounts) {
    const b = c === 1 ? "1 (only itself)" : c <= 3 ? "2-3" : c <= 10 ? "4-10" : "11+";

    hist[b] = (hist[b] ?? 0) + 1;
}

console.log("\n2. HOW MANY READINGS DOES EACH FAILURE'S OWN KEY ALREADY CARRY?\n");
console.log("  readings at that exact key    failures");

for (const b of ["1 (only itself)", "2-3", "4-10", "11+"]) {
    if (hist[b]) {
        console.log(`  ${b.padEnd(28)}${String(hist[b]).padStart(5)}`
            + `   ${(hist[b] / fails.length * 100).toFixed(1)}%`);
    }
}

console.log("\n  EVERY failure is already in the corpus by definition, so the");
console.log("  fitter has been shown the reference's answer for those exact");
console.log("  inputs and still gets it wrong. Another reading at the same key");
console.log("  is a copy of something already held.");

// ------------------------------------------------- 3. where the failures sit
console.log("\n3. THE GROUPS CARRYING THE FAILURES, worst first\n");
console.log("  group                        readings   failures   rate");

const worst = [...byGroup].filter(([, g]) => g.bad > 0)
    .sort((a, b) => b[1].bad - a[1].bad).slice(0, 12);

for (const [k, g] of worst) {
    const [rung, spr] = k.split("|");

    console.log(`  ${`${rung} ${spr}spr`.padEnd(28)}${String(g.n).padStart(8)}   `
        + `${String(g.bad).padStart(8)}   ${(g.bad / g.n * 100).toFixed(1).padStart(5)}%`);
}

const singles = [...byGroup.values()].filter((g) => g.bad === 1).length;

console.log(`\n  and ${singles} groups carry exactly ONE failure each`
    + ` - a group with one bad reading out of many is not a group short of data.`);
