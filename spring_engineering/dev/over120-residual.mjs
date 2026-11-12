// WHAT IS LEFT PAST 120", AFTER THE CORRECTION IS ALREADY APPLIED.
//
//   node dev/over120-residual.mjs
//
// THE GAP IN EVERY PREVIOUS MEASUREMENT OF THIS BAND. `dev/over120.mjs`
// measured the error BEFORE any correction existed - one-sided, 143 long
// against 4 short, growing with distance past the line. That is what
// justified the per-rung constants. **Nobody has looked at the residual
// afterwards**, so "61.57% and the rest is reference noise" is an assumption
// rather than a finding.
//
// Three things decide whether more can be taken, and they are the same three
// named before the first correction was fitted:
//
//   - STILL ONE-SIDED -> there is bias left and a second term can take it
//   - STILL GROWING with length -> the form is wrong, not just the constant
//   - QUANTISED at whole inches -> the rule is a step, not a constant, and a
//     step function per rung would beat a number per rung
//
// If it is symmetric, flat and unquantised, this form is spent and the honest
// move is a product change rather than a model change: say the figures are an
// extrapolation past what Service Spring supports, rather than quietly
// printing a number nobody stands behind.
//
// THE CORRECTION IS LEFT INSTALLED FOR THIS - deliberately, and it is the
// opposite of the rule in dev/derive-over120.mjs. That script must FIT on
// uncorrected output or it fits a correction on top of itself; this one must
// MEASURE corrected output, because the residual is the question. Same engine,
// opposite requirement, which is exactly why it cost a near-miss to learn.
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

    const s = c.duplexStep;

    if (!s) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;

    // Wire misses excluded - a different wire is a different spring.
    if (rung !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const refMax = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);

    if (refMax <= 120) continue;

    rows.push({
        rung,
        springs: c.duplexSpringCount,
        refIn: r.expect.duplexInnerLength,
        ourIn: c.duplexInnerLength,       // ALREADY CORRECTED
        d: c.duplexInnerLength - r.expect.duplexInnerLength,
        past: refMax - 120,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

const med = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
};

console.log(`${rows.length} past-120" readings with the wire right, `
    + `${rows.filter((x) => !x.ok).length} still failing\n`);

// --------------------------------------------------- 1. is bias left?
const ds = rows.map((x) => x.d);
const bad = rows.filter((x) => !x.ok);

console.log("1. IS THERE BIAS LEFT?  (ours - reference, after the correction)\n");
console.log(`  all ${rows.length}:  median ${med(ds).toFixed(2)}  `
    + `mean ${(ds.reduce((a, b) => a + b, 0) / ds.length).toFixed(2)}  `
    + `short ${ds.filter((x) => x < 0).length}  long ${ds.filter((x) => x > 0).length}`);
console.log(`  the ${bad.length} failing:  median `
    + `${med(bad.map((x) => x.d)).toFixed(2)}  `
    + `short ${bad.filter((x) => x.d < 0).length}  `
    + `long ${bad.filter((x) => x.d > 0).length}`);
console.log("\n  BEFORE the correction this read 143 long against 4 short.");
console.log("  A balanced split now means the bias is gone and no further");
console.log("  constant can win; still one-sided means there is more to take.");

// --------------------------------------------------- 2. does it still grow?
console.log(`\n2. DOES THE ERROR STILL GROW WITH DISTANCE PAST 120"?\n`);
console.log("  past 120    n    exact    median d    short  long");

for (const [lo, hi] of [[0, 10], [10, 25], [25, 50], [50, 100], [100, 1e9]]) {
    const g = rows.filter((x) => x.past > lo && x.past <= hi);

    if (!g.length) continue;

    const gd = g.map((x) => x.d);

    console.log(`  ${`${lo}-${hi === 1e9 ? "+" : hi}"`.padEnd(10)}`
        + `${String(g.length).padStart(5)}  `
        + `${(g.filter((x) => x.ok).length / g.length * 100).toFixed(1).padStart(5)}%  `
        + `${med(gd).toFixed(2).padStart(8)}    `
        + `${String(gd.filter((x) => x < 0).length).padStart(4)}  `
        + `${String(gd.filter((x) => x > 0).length).padStart(4)}`);
}

// --------------------------------------------------- 3. is it quantised?
console.log("\n3. IS WHAT IS LEFT QUANTISED?  residuals on the failing readings\n");

const hist = new Map();

for (const x of bad) hist.set(x.d, (hist.get(x.d) ?? 0) + 1);

console.log("  " + [...hist].sort((a, b) => a[0] - b[0])
    .map(([k, v]) => `${k > 0 ? "+" : ""}${k}":${v}`).join("  "));

const whole = bad.filter((x) => Number.isInteger(x.d)).length;

console.log(`\n  whole inches: ${whole} of ${bad.length} `
    + `(${(whole / bad.length * 100).toFixed(0)}%)`);
console.log("  A pile at +1 and +2 with little between is a STEP rule the");
console.log("  constants are averaging over. A spread is noise.");

// --------------------------------------------------- 4. where they sit
console.log("\n4. THE RUNGS STILL CARRYING FAILURES\n");
console.log("  rung                n   failing   median d");

const byRung = new Map();

for (const x of rows) {
    if (!byRung.has(x.rung)) byRung.set(x.rung, []);

    byRung.get(x.rung).push(x);
}

for (const [rg, g] of [...byRung].sort((a, b) =>
    b[1].filter((x) => !x.ok).length - a[1].filter((x) => !x.ok).length).slice(0, 10)) {
    const f = g.filter((x) => !x.ok);

    if (!f.length) continue;

    console.log(`  ${rg.padEnd(18)}${String(g.length).padStart(4)}   `
        + `${String(f.length).padStart(7)}   ${med(f.map((x) => x.d)).toFixed(2).padStart(8)}`);
}

// --------------------------------------------------- 5. could a second term win?
// Tried HERE rather than in the deriver, because this is a residual question:
// is there a global function of distance that the per-rung constants left
// behind? One parameter, grid-searched, scored on everything - optimistic by
// construction, so if it cannot win even in-sample there is nothing there.
console.log("\n5. COULD A SECOND TERM WIN, even fitted in-sample?\n");

const snap = (x) => {
    const lo = Math.floor(x);
    return [lo, lo + 0.25, lo + 1].reduce((a, b) =>
        (Math.abs(b - x) < Math.abs(a - x) ? b : a));
};
const scoreWith = (f) => rows.filter((x) => {
    const adj = f(x);
    return snap(x.ourIn - adj) === x.refIn
        && snap(x.ourIn + 1 - adj) === x.refIn + 1;
}).length;

console.log(`  as it stands                     `
    + `${scoreWith(() => 0)} / ${rows.length}`);

let best = { label: "none", hit: scoreWith(() => 0) };

for (const b of [0.002, 0.005, 0.01, 0.02, 0.03, 0.05]) {
    const hit = scoreWith((x) => b * x.past);

    if (hit > best.hit) best = { label: `+${b} per inch past 120`, hit };
}

for (const a of [0.25, 0.5, 0.75, 1]) {
    const hit = scoreWith(() => a);

    if (hit > best.hit) best = { label: `a further flat ${a}"`, hit };
}

console.log(`  best single extra term:          ${best.hit} / ${rows.length}`
    + `   (${best.label})`);
console.log("\n  In-sample and therefore optimistic. A gain of a handful here");
console.log("  would not survive split-half; a gain of zero settles it.");
