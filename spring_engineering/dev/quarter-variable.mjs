// WHAT DECIDES THE QUARTER, WHERE THE ACTIVE LENGTH DOES NOT?
//
//   node dev/quarter-variable.mjs
//
// THE SETUP, from dev/factor-bonus.mjs. At two springs - the only count where
// `duplexSnapToGrid` leaves the choice live - the bonus factors into
//
//     bonus = step (0 or 1) + quarter (0 or 0.25)
//
// and the two behave completely differently. The STEP is predictable from
// (floor, frac) on every rung, 91.7% to 99.1% cross-validated. The QUARTER
// splits into two populations:
//
//   predictable    96-99%   0.3437/0.273, 0.295/0.2343, 0.3625/0.283, ...
//   near chance    56-79%   0.3938/0.3195, 0.375/0.3065, 0.4615/0.375, ...
//
// So on roughly half the rungs, WHETHER THE REFERENCE LIFTS TO THE QUARTER IS
// NOT A FUNCTION OF THE ACTIVE LENGTH. Something else decides it, and nothing
// in the model looks at anything else.
//
// WHY THIS IS NOT THE MISSING-VARIABLE TEST ALREADY RUN AND LOST. That one
// (dev/missing-variable.mjs, 2026-11-13) asked whether any input predicts
// which side of ITS THRESHOLD a reading falls, pooled over every group - and
// the lesson it recorded was to ask the question where it lives, because easy
// readings drown it. This asks a different and much narrower question: one
// binary decision, on the rungs where it is currently unexplained.
//
// READ THE BASELINE COLUMN FIRST. The quarter is not balanced - a rung that
// is 70% "no quarter" scores 70% by always saying no. A candidate has to beat
// THAT, not 50%, and it has to beat what (floor, frac) already gets.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));

// The rungs factor-bonus.mjs found the quarter unexplained on.
const WEAK = new Set([
    "0.3938/0.3195", "0.3437/0.283", "0.4062/0.331", "0.3625/0.295",
    "0.375/0.3065", "0.5312/0.4305", "0.283/0.2343", "0.5/0.4062",
    "0.4615/0.375",
]);

const rows = [];

for (const r of corpus.readings) {
    if (r.expect?.duplexInnerLength === undefined) continue;
    if ((r.state.springs ?? 2) !== 2) continue;

    let c;

    try {
        c = make(mod, r.state);
    } catch {
        continue;
    }

    const st = c.duplexStep;

    if (!st) continue;

    const rung = `${st.outerWire}/${st.innerWire}`;

    if (!WEAK.has(rung)) continue;
    if (`${st.outerWire}/${st.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const active = c.duplexActiveLength;

    if (!(active > 0)) continue;

    const floor = Math.floor(active);
    const bonus = Number((r.expect.duplexInnerLength - floor).toFixed(2));
    const whole = Math.floor(bonus);
    const q = Number((bonus - whole).toFixed(2));

    if (!((whole === 0 || whole === 1) && (q === 0 || q === 0.25))) continue;

    const heightInches = Number(r.state.doorHeightFeet || 0) * 12
        + Number(r.state.doorHeightInches || 0);
    const weight = Number(r.state.weight) || 0;

    rows.push({
        rung, quarter: q === 0.25,
        floor, frac: active - floor, active,
        height: heightInches,
        weight,
        perSpring: weight / 2,
        cycles: Number(String(r.state.cycles).replace(/,/g, "")) || 0,
        radius: r.state.radius === "LHR" ? 10 : Number(r.state.radius) || 15,
        tippt: c.duplexTipptExact,
        turns: c.turnsExact,
        // The length itself, in case the quarter tracks the ANSWER's size
        // rather than any input - which would be a snap, not a rule.
        refLen: r.expect.duplexInnerLength,
    });
}

const CANDIDATES = [
    ["frac (control)", (r) => r.frac],
    ["floor (control)", (r) => r.floor],
    ["active length", (r) => r.active],
    ["door height", (r) => r.height],
    ["door weight", (r) => r.weight],
    ["lb per spring", (r) => r.perSpring],
    ["cycle target", (r) => r.cycles],
    ["track radius", (r) => r.radius],
    ["tippt", (r) => r.tippt],
    ["turns", (r) => r.turns],
    ["reference length", (r) => r.refLen],
    ["frac of tippt", (r) => (r.tippt * 10) % 1],
    ["frac of refLen", (r) => (r.refLen * 4) % 1],
];

// One threshold on one variable, both polarities, fitted by scanning every
// midpoint between adjacent values.
function fitOne(train, value) {
    const pts = train.map((r) => ({ v: value(r), y: r.quarter }))
        .sort((a, b) => a.v - b.v);
    let best = null;

    for (let i = 0; i <= pts.length; i++) {
        for (const hiVal of [true, false]) {
            const ok = pts.slice(0, i).filter((p) => p.y === !hiVal).length
                + pts.slice(i).filter((p) => p.y === hiVal).length;

            if (!best || ok > best.ok) {
                best = {
                    ok, hiVal,
                    cut: i === 0 ? pts[0].v - 1
                        : i === pts.length ? pts[pts.length - 1].v + 1
                            : (pts[i - 1].v + pts[i].v) / 2,
                };
            }
        }
    }

    return best;
}

function cvOne(rs, value) {
    let right = 0, total = 0;

    for (let k = 0; k < 5; k++) {
        const train = rs.filter((_, i) => i % 5 !== k);
        const test = rs.filter((_, i) => i % 5 === k);

        if (!train.length || !test.length) continue;

        const rule = fitOne(train, value);

        for (const r of test) {
            total += 1;
            right += ((value(r) > rule.cut) === rule.hiVal) === r.quarter ? 1 : 0;
        }
    }

    return total ? right / total : -1;
}

const pct = (x) => (x < 0 ? "   -  " : `${(100 * x).toFixed(1)}%`.padStart(6));

console.log("=".repeat(78));
console.log(`PREDICTING THE QUARTER on ${rows.length} readings over `
    + `${new Set(rows.map((r) => r.rung)).size} rungs where the active length cannot`);
console.log("=".repeat(78));

const base = Math.max(
    rows.filter((r) => r.quarter).length,
    rows.filter((r) => !r.quarter).length
) / rows.length;

console.log(`  always answering the commoner way: ${pct(base)}   <- the baseline to beat\n`);
console.log("  candidate              pooled cv     best rung     worst rung");

for (const [name, value] of CANDIDATES) {
    const pooled = cvOne(rows, value);
    const per = [...new Set(rows.map((r) => r.rung))]
        .map((rg) => cvOne(rows.filter((r) => r.rung === rg), value))
        .filter((x) => x >= 0);

    console.log(`  ${name.padEnd(22)}${pct(pooled)}       ${pct(Math.max(...per))}        ${pct(Math.min(...per))}`);
}

console.log("\n  Per rung, the quarter's own balance - a rung that is nearly all one");
console.log("  way has little to predict and its score means little:");
console.log("    rung                n   quarter   share");

for (const rg of [...new Set(rows.map((r) => r.rung))].sort()) {
    const g = rows.filter((r) => r.rung === rg);
    const q = g.filter((r) => r.quarter).length;

    console.log(`    ${rg.padEnd(18)}${String(g.length).padStart(4)}${String(q).padStart(9)}`
        + `   ${(100 * q / g.length).toFixed(0)}%`);
}
