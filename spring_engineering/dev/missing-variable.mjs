// IS THERE A MISSING INPUT IN THE BONUS DECISION?
//
//   node dev/missing-variable.mjs
//
// WHY THIS IS THE RIGHT QUESTION AND "REFIT THE STIFFNESS MODEL" IS NOT.
// A two-level group decides by `frac > a + b*floor`, which is
// `active > floor*(1+b) + a`. Scaling `duplexActiveLength` by (1+eps) moves
// frac by about eps*floor - which is EXACTLY a change in `b`. **The fitted
// slope already absorbs any linear scale error in the active length**, per
// rung and per spring count. So refitting sMult or K cannot win: the fitter
// has been undoing that error all along.
//
// What `b` cannot absorb is error that varies with something OTHER than
// floor. So the only way a more accurate active length helps is if its error
// correlates with a variable the decision does not currently see.
//
// THE TEST. dev/miss-margin.mjs shows the failures hug the boundary (median
// |margin| 0.0133 against 0.2490 overall) and STRADDLE it (30 want lo, 33
// want hi), so no placement of the line wins. But if some variable V shifts
// the true boundary, then scoring on `margin - c*V` beats scoring on `margin`
// alone - and c is one number.
//
// THE NOISE FLOOR IS MEASURED FIRST, which is yesterday's lesson written into
// a tool: the LINE_SLACK screen reported +10 and +4 readings as findings when
// the per-fold standard deviation was 10.5. Nothing here is believed until it
// is compared against the spread of the baseline against itself.
//
// AND THE FIRST VERSION OF THIS TEST WAS DOMINATED BY EASY READINGS. Scoring
// a GLOBAL `c` over all 9,398 readings returned EXACTLY the baseline for all
// eleven candidates, because a correction big enough to flip a reading sitting
// 0.01 from its boundary also moves the 8,850 sitting nowhere near one. Every
// fold chose c = 0 and the test could not have detected a real variable.
//
// So the question is asked where it lives: AT THE BOUNDARY. Two ways, and the
// first needs no fitting at all - among readings within a short distance of
// their threshold, does the variable DIFFER between the doors the reference
// sent one way and the doors it sent the other? A variable that carries the
// missing information must separate them.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { makeRnd } from "./rnd.mjs";

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

    const rung = `${step.outerWire}/${step.innerWire}`;

    if (rung !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    if (Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength) > 96) {
        continue;
    }

    const springs = c.duplexSpringCount;
    const split = step.splitByCount && step.splitByCount[springs];
    const act = c.duplexActiveLength;
    const whole = Math.floor(act);
    const line = split
        ? (whole >= split.from ? split.above : split.below)
        : step.lineByCount && step.lineByCount[springs];

    if (!line || line.cuts || line.mid !== undefined) continue;

    const want = r.expect.duplexInnerLength - whole;

    // Only readings the reference answered with one of this group's two
    // levels - the seven that wanted neither are outside the form and no
    // boundary, moved or not, can reach them.
    if (want !== line.lo && want !== line.hi) continue;

    const st = r.state;
    const height = Number(st.doorHeightFeet) * 12 + Number(st.doorHeightInches || 0);
    const weight = Number(st.weight);

    rows.push({
        group: `${rung}|${springs}`,
        margin: (act - whole) - (line.a + line.b * whole),
        wantHi: want === line.hi,
        // every candidate the decision does not currently see
        v: {
            height,
            weight,
            lbPerSpring: weight / springs,
            cycles: Number(String(st.cycles).replace(/,/g, "")),
            radius: st.radius === "LHR" ? 10 : Number(st.radius),
            hiLift: st.liftType === "Hi-Lift" ? Number(st.liftin || 0) : 0,
            active: act,
            // controls: `b` already absorbs anything linear in floor, so
            // these two must come out near zero or the test is broken
            floor: whole,
            frac: act - whole,
            // the torque quantities, which is where a stiffness error lives
            turns: Number(c.duplexTurns) || 0,
            ippt: Number(c.duplexTipptExact) || 0,
        },
    });
}

const KEYS = Object.keys(rows[0].v);

// Centre and scale each variable so one `c` ladder covers them all.
const stats = {};

for (const k of KEYS) {
    const xs = rows.map((x) => x.v[k]);
    const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
    const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length) || 1;

    stats[k] = { mean, sd };
}

for (const x of rows) {
    x.z = {};
    for (const k of KEYS) x.z[k] = (x.v[k] - stats[k].mean) / stats[k].sd;
}

const score = (set, k, c) => set.filter((x) =>
    ((x.margin - c * (k ? x.z[k] : 0)) > 0) === x.wantHi).length;

console.log(`${rows.length} in-envelope readings in plain two-level groups`);
console.log(`${rows.filter((x) => (x.margin > 0) !== x.wantHi).length} `
    + `currently on the wrong side of their boundary\n`);

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / (xs.length || 1);

// ============================ 1. SEPARATION AT THE BOUNDARY, no fitting
// Among readings close to their threshold, split by the answer the reference
// gave and compare each variable. Welch's t: a variable carrying the missing
// information must pull the two sets apart. |t| over about 3 is worth looking
// at on this many readings; under 2 is nothing.
console.log("1. AT THE BOUNDARY, DO THE TWO ANSWERS DIFFER IN ANY VARIABLE?\n");

for (const BAND of [0.02, 0.05, 0.1]) {
    const near = rows.filter((x) => Math.abs(x.margin) < BAND);
    const hi = near.filter((x) => x.wantHi);
    const lo = near.filter((x) => !x.wantHi);

    console.log(`  |margin| < ${BAND}   ${near.length} readings  `
        + `(${hi.length} want hi, ${lo.length} want lo)`);

    const out = [];

    for (const k of KEYS) {
        const a = hi.map((x) => x.z[k]);
        const b = lo.map((x) => x.z[k]);

        if (a.length < 5 || b.length < 5) continue;

        const ma = mean(a), mb = mean(b);
        const va = mean(a.map((x) => (x - ma) ** 2)) / a.length;
        const vb = mean(b.map((x) => (x - mb) ** 2)) / b.length;
        const t = (ma - mb) / Math.sqrt(va + vb || 1e-12);

        out.push({ k, t });
    }

    out.sort((x, y) => Math.abs(y.t) - Math.abs(x.t));
    console.log("    " + out.map((o) =>
        `${o.k} ${o.t >= 0 ? "+" : ""}${o.t.toFixed(1)}`).join("   "));
    console.log("");
}

console.log("  `margin` itself is NOT in this list, so a large |t| would be");
console.log("  information the boundary does not already have. `floor` and");
console.log("  `frac` are CONTROLS - the fitted slope b already absorbs");
console.log("  anything linear in floor, so a big score on either means the");
console.log("  test is wrong rather than that something was found.\n");

// ============================ 2. CAN IT PREDICT? scored in the band only
// The noise floor first, then each candidate, with `c` fitted on one half of
// the band and scored on the other.
const BAND = 0.05;
const band = rows.filter((x) => Math.abs(x.margin) < BAND);

console.log(`2. CAN ANY OF THEM PREDICT THE SIDE?  (|margin| < ${BAND}, `
    + `${band.length} readings)\n`);

const SEEDS = [11131, 11132, 11133, 11134, 11135, 11136, 11137, 11138];
const halves = [];

for (const seed of SEEDS) {
    const { rnd } = makeRnd(seed);
    const sh = band.slice();

    for (let i = sh.length - 1; i > 0; i--) {
        const j = Math.floor(rnd() * (i + 1));

        [sh[i], sh[j]] = [sh[j], sh[i]];
    }

    const h = Math.floor(sh.length / 2);

    halves.push([sh.slice(0, h), sh.slice(h)], [sh.slice(h), sh.slice(0, h)]);
}

const base = halves.map(([, te]) => score(te, null, 0));
const bmean = mean(base);
const bsd = Math.sqrt(base.reduce((a, b) => a + (b - bmean) ** 2, 0)
    / (base.length - 1));

console.log("  THE NOISE FLOOR FIRST - baseline on each half, nothing changed:");
console.log(`    mean ${bmean.toFixed(1)} of ${Math.floor(band.length / 2)}`
    + `   sd ${bsd.toFixed(2)}   over ${halves.length} half-sets`);
console.log(`    a candidate must beat it by more than about `
    + `${(2 * bsd).toFixed(1)} readings.\n`);

const CS = [];

for (let c = -0.1; c <= 0.1001; c += 0.002) CS.push(Math.round(c * 1000) / 1000);

console.log("  variable          out of sample   vs baseline");

const results = [];

for (const k of KEYS) {
    let tot = 0;

    for (const [tr, te] of halves) {
        let bestC = 0, bestHit = -1;

        for (const c of CS) {
            const h = score(tr, k, c);

            if (h > bestHit) { bestHit = h; bestC = c; }
        }

        tot += score(te, k, bestC);
    }

    results.push({ k, m: tot / halves.length, d: tot / halves.length - bmean });
}

for (const { k, m, d } of results.sort((a, b) => b.m - a.m)) {
    const verdict = d > 2 * bsd ? "  <- BEATS THE NOISE FLOOR"
        : d > 0 ? "   (inside the noise)" : "";

    console.log(`  ${k.padEnd(16)}${m.toFixed(1).padStart(10)}`
        + `${(d >= 0 ? "+" : "") + d.toFixed(1)}`.padStart(14) + verdict);
}

console.log(`\n  baseline          ${bmean.toFixed(1)}`);
console.log("\n  NOTHING BEATING THE FLOOR means the straddlers carry no");
console.log("  recoverable signal in any input we hold, and the in-envelope");
console.log("  failures are irreducible at this precision.");
