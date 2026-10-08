// The GRID the reference's Duplex lengths live on, and whether we match it.
//
//   node dev/grid-survey.mjs
//
// Reads every dev/*.json that carries reference readings for the 3 3/4" inside
// 6" pair, dedupes by geometry, and reports the fractional part of the inner
// length - what values it takes, what decides them, and whether the model
// reproduces the rule.
//
// WHAT IT FOUND. The fraction is only ever .00 or .25 - never .5, never .75 -
// and it is all but determined by the SPRING COUNT:
//
//     1 spring    0.0% carry .25        3 springs  100.0%
//     2 springs  30.3%                  4 springs  100.0%
//
// Inner and outer always agree on the fraction, and the pair is always exactly
// 1.00" apart.
//
// AND WHY IT IS HERE RATHER THAN IN A FIX. That rule looks like free accuracy
// until you check: the model already reproduces it at 100%, 99.0%, 100%, 100%,
// disagreeing on 17 of 4,472 readings and on none it otherwise gets right. The
// three-regime rounding already carries it. Run this before changing anything
// about the snap - a tool that shows the rule is already honoured is worth more
// than the afternoon spent re-deriving it.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { stateFromReading, isClean, isModelledDuplex } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const isQuarter = (x) => Math.abs(x - Math.floor(x) - 0.25) < 1e-6;
const seen = new Set();
const rows = [];
const fracs = new Map();

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
        const i = r.input, d = r.data;

        if (!i || !d || r.error || !isModelledDuplex(i) || !isClean(r)) continue;

        const inn = d.innerSpring, out = d.outerSpring;

        if (!inn?.springLength || !out?.springLength || !inn.wireSize) continue;

        // One row per geometry. The same door appears in several pulls, and a
        // boundary-dense sweep would otherwise dominate a share.
        const key = [i.drum, i.springs, i.radius, i.lift, i.hiLift ?? "",
            i.cycles, i.weight, i.heightInches].join("|");

        if (seen.has(key)) continue;

        seen.add(key);

        const fr = +(inn.springLength - Math.floor(inn.springLength)).toFixed(4);

        fracs.set(fr, (fracs.get(fr) || 0) + 1);

        let c, s;

        try { c = make(mod, stateFromReading(i)); s = c.duplexStep; } catch { continue; }

        if (!s) continue;

        const wireOk = `${s.outerWire}/${s.innerWire}`
            === `${parseFloat(out.wireSize)}/${parseFloat(inn.wireSize)}`;

        rows.push({
            springs: i.springs ?? 2, wireOk,
            refQ: isQuarter(inn.springLength),
            outerQ: isQuarter(out.springLength),
            gap: out.springLength - inn.springLength,
            ourQ: c.duplexInnerLength == null ? null : isQuarter(c.duplexInnerLength),
            exact: c.duplexInnerLength === inn.springLength,
        });
    }
}

const total = [...fracs.values()].reduce((a, b) => a + b, 0);

console.log(`deduped reference readings on the modelled pair: ${total}\n`);
console.log("fractional part of the inner length:");

for (const [k, v] of [...fracs].sort((a, b) => b[1] - a[1])) {
    console.log(`  .${String(Math.round(k * 100)).padStart(2, "0")}   ${String(v).padStart(5)}`
        + `   ${(100 * v / total).toFixed(1)}%`);
}

const pc = (a, b) => (b ? `${(100 * a / b).toFixed(1)}%` : "   -  ");

console.log(`\ninner and outer agree on the fraction: `
    + `${pc(rows.filter((p) => p.refQ === p.outerQ).length, rows.length)}`);
console.log(`pair exactly 1.00" apart:              `
    + `${pc(rows.filter((p) => Math.abs(p.gap - 1) < 1e-9).length, rows.length)}`);

const scored = rows.filter((p) => p.wireOk && p.ourQ !== null);

console.log("\nby spring count, on readings where the wire agrees:");
console.log("  springs      n    ref .25   ours .25   frac agrees   length exact");

for (const s of [1, 2, 3, 4]) {
    const v = scored.filter((p) => p.springs === s);

    if (!v.length) continue;

    console.log(`     ${s}    ${String(v.length).padStart(5)}    `
        + `${pc(v.filter((p) => p.refQ).length, v.length).padStart(7)}`
        + `   ${pc(v.filter((p) => p.ourQ).length, v.length).padStart(8)}`
        + `   ${pc(v.filter((p) => p.refQ === p.ourQ).length, v.length).padStart(11)}`
        + `   ${pc(v.filter((p) => p.exact).length, v.length).padStart(12)}`);
}

const bad = scored.filter((p) => p.refQ !== p.ourQ);

console.log(`\nfraction disagrees on ${bad.length}/${scored.length}`
    + ` = ${pc(bad.length, scored.length)}, of which length exact: ${bad.filter((p) => p.exact).length}`);
