// HYPOTHESIS: the bonus threshold is linear in the INTEGER part of the active
// length, not constant in frac.
//
// The band model keys the bonus on frac(active) alone, and that provably
// cannot work: on 0.3625/0.283 at one spring, frac 0.815 wants +1 at active
// 17.815 and 0 at active 25.816. Same rung, same spring count, same frac,
// different answer. What separates them is the integer part.
//
// For each (rung, spring count, floor) this prints the interval the threshold
// must lie in - above the largest frac taking the low bonus, at or below the
// smallest frac taking the high one - and then checks whether ONE line
// through floor can satisfy every interval at once.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
const c = JSON.parse(readFileSync("./dev/corpus.json", "utf8"));
const obs = new Map();

for (const r of c.readings) {
    if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) continue;
    const comp = make(mod, r.state);
    const step = comp.duplexStep;
    if (!step) continue;
    const refW = `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
    if (`${step.outerWire}/${step.innerWire}` !== refW) continue;
    const act = comp.duplexActiveLength;
    if (!(act > 0)) continue;
    const key = `${refW}|${comp.duplexSpringCount}`;
    (obs.get(key) ?? obs.set(key, []).get(key)).push({
        F: Math.floor(act), t: act - Math.floor(act),
        bonus: r.expect.duplexInnerLength - Math.floor(act),
    });
}

let fits = 0, total = 0;
for (const [key, rows] of [...obs].sort()) {
    // Only the two-bonus-value case is a simple threshold; report the rest.
    const vals = [...new Set(rows.map((r) => r.bonus))].sort((a, b) => a - b);
    if (rows.length < 12 || vals.length !== 2) continue;
    const [lo, hiB] = vals;
    const byF = new Map();
    for (const r of rows) {
        const e = byF.get(r.F) ?? { loMax: -1, hiMin: 2 };
        if (r.bonus === lo) e.loMax = Math.max(e.loMax, r.t);
        else e.hiMin = Math.min(e.hiMin, r.t);
        byF.set(r.F, e);
    }
    // Buckets that actually constrain the line (both bonuses seen, or one-sided).
    const cons = [...byF].filter(([, e]) => e.loMax >= 0 || e.hiMin <= 1).sort((a, b) => a[0] - b[0]);
    if (cons.length < 3) continue;
    total += 1;
    // Fit t = a + b*F by brute force over a small grid; any line satisfying all.
    let best = null;
    for (let b = -0.02; b <= 0.08; b += 0.0005) {
        for (let a = -1.5; a <= 1.5; a += 0.005) {
            let bad = 0;
            for (const [F, e] of cons) {
                const thr = a + b * F;
                if (e.loMax >= 0 && thr <= e.loMax) bad += 1;
                if (e.hiMin <= 1 && thr > e.hiMin) bad += 1;
            }
            if (!best || bad < best.bad) best = { a, b, bad };
            if (!bad) break;
        }
        if (best && !best.bad) break;
    }
    const ok = best.bad === 0;
    if (ok) fits += 1;
    console.log(`${key.padEnd(22)} ${String(rows.length).padStart(4)} readings, ${cons.length} buckets  ` +
        `bonus ${lo}/${hiB}  -> ${ok ? `LINE FITS  t = ${best.a.toFixed(3)} + ${best.b.toFixed(4)}*floor` : `${best.bad} violation(s)`}`);
}
console.log(`\n${fits}/${total} two-bonus groups are explained by ONE line in floor(active).`);
