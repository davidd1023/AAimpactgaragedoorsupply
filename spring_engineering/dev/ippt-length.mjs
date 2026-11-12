// IS THE LENGTH DERIVABLE FROM THE REQUIRED IPPT, INSTEAD OF FROM A FITTED
// BONUS TABLE?
//
//   node dev/ippt-length.mjs
//
// THE ONE IDEA LEFT about the FORM of the duplex length rule, and the only
// one that ever came from outside this repository. Every other lever has been
// tried and lost, each recorded in CLAUDE.md: more data (batch S2 moved
// nothing), more model capacity globally and per group (both lose 2+ points
// on never-tuned data), and "length = total coils x wire" from the vendor's
// own ordering guide (tested properly 2026-11-11 and refuted - the residual
// is perfectly flat in coils).
//
// THE FORM. Torsion coils are wound closed and touching, so the published
// engineering relation is
//
//     IPPT = (E d^4) / (10.8 D N)     with N = L / d
//          = (E d^5) / (10.8 D L)
//
// which inverts to a LENGTH:
//
//     L = (E d^5) / (10.8 D x IPPT_per_spring)
//
// If that is what the reference does, then the fifty fitted rung lines are
// reproducing one constant E and a snap to the quarter-inch grid - and the
// per-rung bonus exists only because d differs per rung.
//
// WHY THIS WAS RECORDED AS BLOCKED, AND WHY IT IS NOT.
//
// CLAUDE.md says closing it "needs the REQUIRED IPPT (what the door demands),
// not the reference's reported total, which is an output of its own choice
// and makes any test circular". That was right about the reference's figure
// and WRONG that we have no other - the engine computes `duplexTipptExact`
// from weight x rEff / turns, which are the DOOR's own inputs (weight, height,
// drum, radius) and contain nothing the reference said. It is a required
// IPPT, not a reported one.
//
// So STEP 1 below checks our required figure against the reference's reported
// one. Agreement means the quantity is sound and the inversion is not
// circular; disagreement means stop, and says by how much.
//
// STEP 2 then inverts it and SCORES, which is the whole point: a hypothesis
// about the form is worth exactly what it predicts on readings it never saw.
// Nothing here writes to the engine or the table - this measures, and if it
// wins, implementing it is a separate and much larger job.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { stateFromReading, isModelledDuplex, isClean } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();

// 10.8 and the mean-diameter convention are the published form's, not ours.
const K = 10.8;
const ippt = (E, d, id, L) => (E * d ** 5) / (K * (id + d) * L);

// Every pull output that carries the reference's own IPPT. The corpus only
// began storing it on 2026-11-11 (see import.mjs), so the pulls are where the
// history is - 4,600-odd readings that were on disk the whole time.
const rows = [];

for (const f of readdirSync(HERE).filter((x) => /\.json$/.test(x))) {
    let j;

    try { j = JSON.parse(readFileSync(join(HERE, f), "utf8")); } catch { continue; }

    if (!Array.isArray(j)) continue;

    for (const r of j) {
        if (!r || !r.data || r.data.totalInchPoundPerTurn === undefined) continue;
        if (!r.input || !r.data.innerSpring || !r.data.outerSpring) continue;
        if (!isModelledDuplex(r.input)) continue;

        rows.push({ file: f, input: r.input, data: r.data, clean: isClean(r) });
    }
}

console.log(`${rows.length} readings carry the reference's own IPPT `
    + `(${rows.filter((r) => r.clean).length} clean)\n`);

// ---------------------------------------------------------------- step 1
// OUR REQUIRED IPPT vs THEIR REPORTED ONE.
const cmp = [];

for (const r of rows) {
    if (!r.clean) continue;

    let comp;

    try { comp = make(mod, stateFromReading(r.input)); } catch { continue; }

    const ours = comp.duplexTipptExact;

    if (!(ours > 0)) continue;

    cmp.push({
        r, ours, theirs: Number(r.data.totalInchPoundPerTurn),
        turnsOurs: comp.turnsExact, turnsTheirs: Number(r.data.turnsOnSprings),
        comp,
    });
}

const pct = (a, b) => Math.abs(a - b) / b * 100;
const med = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
};

const dI = cmp.map((x) => pct(x.ours, x.theirs));
const dT = cmp.map((x) => pct(x.turnsOurs, x.turnsTheirs));

console.log("STEP 1  is our REQUIRED ippt the same quantity as their REPORTED one?");
console.log(`  n ${cmp.length}`);
console.log(`  IPPT   median err ${med(dI).toFixed(3)}%   `
    + `within 1%: ${(dI.filter((x) => x < 1).length / dI.length * 100).toFixed(1)}%   `
    + `within 5%: ${(dI.filter((x) => x < 5).length / dI.length * 100).toFixed(1)}%`);
console.log(`  turns  median err ${med(dT).toFixed(3)}%   `
    + `within 1%: ${(dT.filter((x) => x < 1).length / dT.length * 100).toFixed(1)}%`);

if (med(dI) > 2) {
    console.log("\n  THE QUANTITIES DISAGREE. The inversion below is meaningless; stop here.");
}

// ---------------------------------------------------------------- step 2
// Fit E on the reference's OWN springs (its lengths, its wires, its reported
// IPPT). This is the calibration step and it is allowed to see the answers -
// it is one constant.
const es = [];

for (const x of cmp) {
    const { innerSpring: i, outerSpring: o } = x.r.data;
    const n = x.comp.duplexSpringCount;
    // total = springs x (inner + outer), each at E=1, so E is the ratio
    const unit = n * (ippt(1, i.wireSize, 3.75, i.springLength)
        + ippt(1, o.wireSize, 6, o.springLength));

    if (unit > 0) es.push(x.theirs / unit);
}

const E = med(es);
const spread = es.length
    ? es.slice().sort((a, b) => a - b)[Math.floor(es.length * 0.9)]
        / es.slice().sort((a, b) => a - b)[Math.floor(es.length * 0.1)]
    : NaN;

console.log(`\nSTEP 2  E fitted on the reference's own springs: `
    + `${(E / 1e6).toFixed(2)}M psi   p90/p10 ${spread.toFixed(4)}x   n ${es.length}`);

// THE TWO LENGTHS ARE LINKED, so the inversion has one unknown, not two.
// Checked rather than assumed - if the offset is not fixed the inversion
// needs a second relation and this prints what it actually is.
const offs = {};

for (const x of cmp) {
    const d = x.r.data.outerSpring.springLength - x.r.data.innerSpring.springLength;

    offs[d] = (offs[d] ?? 0) + 1;
}

console.log("  outer length - inner length: "
    + Object.entries(offs).sort((a, b) => b[1] - a[1]).slice(0, 5)
        .map(([k, v]) => `${k}":${v}`).join("  "));

// ---------------------------------------------------------------- step 3
// INVERT IT AND SCORE. Solve the pair for a common inner length L with the
// observed offset, using OUR required IPPT and the wires the model picked,
// then snap to the grid the reference actually uses ({n, n+0.25}).
const OFF = Number(Object.entries(offs).sort((a, b) => b[1] - a[1])[0][0]);
const snap = (x) => {
    const lo = Math.floor(x);
    const cands = [lo, lo + 0.25, lo + 1];
    return cands.reduce((a, b) => (Math.abs(b - x) < Math.abs(a - x) ? b : a));
};

let n = 0, exact = 0, within25 = 0, within1 = 0;
const errs = [];

for (const x of cmp) {
    const step = x.comp.duplexStep;

    if (!step) continue;

    const refW = `${parseFloat(x.r.data.outerSpring.wireSize)}/`
        + `${parseFloat(x.r.data.innerSpring.wireSize)}`;

    // WIRE-ONLY MISSES EXCLUDED, as every length diagnostic here does: a
    // different wire is a different spring and its length is not comparable.
    if (`${step.outerWire}/${step.innerWire}` !== refW) continue;

    // total(L) = springs x [ (E di^5)/(K Di L) + (E do^5)/(K Do (L+OFF)) ]
    // Solved by bisection - the right-hand side is monotone decreasing in L,
    // so this is exact to the tolerance and needs no algebra.
    const spr = x.comp.duplexSpringCount;
    const f = (L) => spr * (ippt(E, step.innerWire, 3.75, L)
        + ippt(E, step.outerWire, 6, L + OFF)) - x.ours;

    let lo = 1, hi = 400;

    if (f(lo) < 0 || f(hi) > 0) continue;

    for (let k = 0; k < 80; k++) {
        const mid = (lo + hi) / 2;

        if (f(mid) > 0) lo = mid; else hi = mid;
    }

    const L = snap((lo + hi) / 2);
    const ref = x.r.data.innerSpring.springLength;

    n++;
    if (L === ref) exact++;
    if (Math.abs(L - ref) <= 0.25) within25++;
    if (Math.abs(L - ref) <= 1) within1++;
    errs.push(Math.abs(L - ref));
}

console.log(`\nSTEP 3  invert the formula for the length and score it`);
console.log(`  n ${n}   EXACT ${(exact / n * 100).toFixed(2)}%   `
    + `within 1/4" ${(within25 / n * 100).toFixed(2)}%   `
    + `within 1" ${(within1 / n * 100).toFixed(2)}%   `
    + `median |err| ${med(errs).toFixed(2)}"`);
console.log(`\n  the installed bonus table scores 98.81% exact on this question.`);
console.log("  A form worth adopting has to beat that, not merely be principled.");
