// WHAT SHAPE IS THE PAST-120" RESIDUAL, AND WHICH FORM FITS IT?
//
//   node dev/over120-levels.mjs            the shape, then the form ladder
//   node dev/over120-levels.mjs shape      the shape only (fast)
//
// THE TOOL THAT FOUND THE TWELFTH FORM, after eleven invented ones lost. It
// does two things in order, and the order is the point:
//
//   1. LOOK AT THE RESIDUAL'S SHAPE. Past the gate every rung's implied bonus
//      takes exactly TWO LEVELS ONE INCH APART - `-1`/`0` on the heavy rungs,
//      `0.25`/`1.25` on `0.2625/0.2253 4spr` - never a spread. A constant per
//      rung can only pick the majority level, which is exactly the 53% it
//      scored. Eleven forms were guessed before anybody looked.
//
//   2. ASK WHAT SEPARATES THE TWO LEVELS, by split-half over five shuffles.
//      Floor of the active length wins; frac, door height, weight and cycle
//      count all lose. Floor is the same variable `splitByCount` splits on
//      in-envelope.
//
// THE CORRECTION MUST BE REMOVED BEFORE ANY OF THIS IS MEASURED, and it is
// NOT reachable off the harness - `mod.DUPLEX_LONG_OFFSET` is undefined, so
// `?? 0` turns a missing export into a plausible zero and every form gets
// fitted on top of the shipped table. That happened: the first run reported a
// 57.6% baseline against a 52.3% correction, which is impossible. The table is
// read from dev/over120-offsets.json here for exactly that reason.
//
// AN OPTIONAL CHAIN IS NOT A SAFE WAY TO READ SOMETHING THAT MUST BE THERE.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { makeRnd } from "./rnd.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
// THE SOURCE OF TRUTH, not the module - see the header.
const OFF = JSON.parse(readFileSync(join(HERE, "over120-offsets.json"), "utf8"));
const offOf = (e, floor) => (!e ? 0
    : typeof e === "number" ? e
        : (e.t === null || floor < e.t ? e.lo : e.hi));
const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const s = c.duplexStep;

    if (!s) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;

    // A wire miss is a different spring; its length is not comparable.
    if (rung !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const floor = Math.floor(c.duplexActiveLength);
    const back = offOf(OFF[rung], floor);           // put the correction back
    const ourIn = c.duplexInnerLength + back;

    if (!(ourIn > 119)) continue;                   // the runtime gate

    rows.push({
        rung, group: `${rung}|${c.duplexSpringCount}`, floor,
        frac: +(c.duplexActiveLength - floor).toFixed(4),
        height: Number(r.state.doorHeightFeet) * 12
            + Number(r.state.doorHeightInches || 0),
        weight: Number(r.state.weight),
        cycles: Number(String(r.state.cycles).replace(/,/g, "")),
        ourIn, ourOut: c.duplexOuterLength + back,
        refIn: r.expect.duplexInnerLength, refOut: r.expect.duplexOuterLength,
        // what the reference implies, as a bonus off our own floor
        level: r.expect.duplexInnerLength - floor,
    });
}

console.log(`${rows.length} past-120" readings with the wire right, `
    + `${new Set(rows.map((x) => x.rung)).size} rungs\n`);

// --------------------------------------------------------------- 1. the shape
console.log("1. HOW MANY LEVELS DOES EACH GROUP'S IMPLIED BONUS TAKE?\n");

const byGroup = new Map();

for (const x of rows) {
    if (!byGroup.has(x.group)) byGroup.set(x.group, []);

    byGroup.get(x.group).push(x);
}

let twoish = 0, shown = 0;

for (const [k, g] of [...byGroup].sort((a, b) => b[1].length - a[1].length)) {
    const h = new Map();

    for (const x of g) h.set(x.level, (h.get(x.level) ?? 0) + 1);

    const lv = [...h].sort((a, b) => a[0] - b[0]);
    const span = lv[lv.length - 1][0] - lv[0][0];

    if (lv.length >= 2 && span <= 1.5) twoish++;

    if (g.length >= 10 && shown++ < 12) {
        const [rung, spr] = k.split("|");

        console.log(`  ${`${rung} ${spr}spr`.padEnd(22)}n=${String(g.length).padStart(3)}`
            + `  levels: ${lv.map(([v, n]) => `${v}:${n}`).join("  ")}`);
    }
}

console.log(`\n  ${twoish} of ${byGroup.size} groups hold two or more levels`
    + ` spanning <= 1.5".`);
console.log("  TWO LEVELS AN INCH APART is what a constant cannot express: it");
console.log("  picks the majority one and loses the other. That is the finding");
console.log("  the first eleven forms were invented instead of looking for.");

if (process.argv[2] === "shape") process.exit(0);

// --------------------------------------------------- 2. what separates them
const snap = (x) => {
    const lo = Math.floor(x);
    return [lo, lo + 0.25, lo + 1].reduce((a, b) =>
        (Math.abs(b - x) < Math.abs(a - x) ? b : a));
};
const hit = (x, off) => snap(x.ourIn - off) === x.refIn
    && snap(x.ourOut - off) === x.refOut;
const OFFSETS = [];

for (let a = -1; a <= 4.001; a += 0.25) OFFSETS.push(Math.round(a * 100) / 100);

const bestOffset = (g) => {
    let best = 0, bestHit = g.filter((x) => hit(x, 0)).length;

    for (const o of OFFSETS) {
        const h = g.filter((x) => hit(x, o)).length;

        if (h > bestHit) { bestHit = h; best = o; }
    }

    return [best, bestHit];
};
const fitConst = (tr) => {
    const m = new Map();

    for (const k of new Set(tr.map((x) => x.rung))) {
        const [b] = bestOffset(tr.filter((x) => x.rung === k));

        if (b !== 0) m.set(k, b);
    }

    return m;
};
// TWO LEVELS, split on f(). The one-constant form is tried first and a split
// must beat it outright, so a rung that wants one level keeps one.
const fitTwo = (tr, f, min) => {
    const m = new Map();

    for (const k of new Set(tr.map((x) => x.rung))) {
        const g = tr.filter((x) => x.rung === k);

        if (g.length < min) continue;

        const [c, ch] = bestOffset(g);
        let best = { hit: ch, t: null, lo: c, hi: c };

        for (const t of [...new Set(g.map(f))].sort((a, b) => a - b)) {
            const below = g.filter((x) => f(x) < t);
            const above = g.filter((x) => f(x) >= t);

            if (below.length < 2 || above.length < 2) continue;

            const [lo, lh] = bestOffset(below);
            const [hi, hh] = bestOffset(above);

            if (lh + hh > best.hit) best = { hit: lh + hh, t, lo, hi };
        }

        m.set(k, best);
    }

    return m;
};

console.log("\n2. SPLIT-HALF OVER FIVE SHUFFLES, both ways round each time.\n");
console.log("  Five, because 600 readings against ~75 parameters is enough");
console.log("  freedom for one lucky split to look like a discovery.\n");

const SEEDS = [20261112, 61006, 20261007, 20261009, 777001];
const VARS = [["floor", (x) => x.floor], ["frac", (x) => x.frac],
    ["height", (x) => x.height], ["weight", (x) => x.weight],
    ["cycles", (x) => x.cycles]];
const tot = rows.length * SEEDS.length;
const acc = { none: 0, konst: 0 };

for (const [nm] of VARS) acc[nm] = 0;

for (const seed of SEEDS) {
    const { rnd } = makeRnd(seed);
    const sh = rows.slice();

    for (let i = sh.length - 1; i > 0; i--) {
        const j = Math.floor(rnd() * (i + 1));

        [sh[i], sh[j]] = [sh[j], sh[i]];
    }

    const half = Math.floor(sh.length / 2);

    for (const [tr, te] of [[sh.slice(0, half), sh.slice(half)],
        [sh.slice(half), sh.slice(0, half)]]) {
        acc.none += te.filter((x) => hit(x, 0)).length;

        const mc = fitConst(tr);

        acc.konst += te.filter((x) => hit(x, mc.get(x.rung) ?? 0)).length;

        for (const [nm, f] of VARS) {
            const mt = fitTwo(tr, f, 8);

            acc[nm] += te.filter((x) => {
                const e = mt.get(x.rung);

                return hit(x, !e ? 0 : (e.t === null || f(x) < e.t ? e.lo : e.hi));
            }).length;
        }
    }
}

const pc = (v) => `${(v / tot * 100).toFixed(2)}%`;

console.log(`  no correction at all                 ${pc(acc.none)}`);
console.log(`  per-rung CONSTANT                    ${pc(acc.konst)}`
    + "   <- the bar\n");
console.log("  per-rung TWO LEVELS, split on:");

for (const [nm] of [...VARS].sort((a, b) => acc[b[0]] - acc[a[0]])) {
    console.log(`    ${nm.padEnd(34)}${pc(acc[nm])}`
        + `   ${acc[nm] > acc.konst
            ? `+${((acc[nm] - acc.konst) / tot * 100).toFixed(2)} points`
            : "loses"}`);
}

console.log("\n  Out of sample over " + tot + " scorings. The winner is what");
console.log("  dev/derive-over120.mjs fits and ships; the losers are recorded");
console.log("  so nobody spends another session inventing a thirteenth form.");
