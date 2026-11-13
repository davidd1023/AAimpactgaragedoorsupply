// IS OUR TURNS WRONG ON HI-LIFT, AND DOES IT EXPLAIN THE TIPPT ERROR?
//
//   node dev/turns-hilift.mjs
//
// THE FIRST STRUCTURED ERROR FOUND IN DAYS, and it was found by following
// the LENGTH residual back to its only reading-specific input.
//
// `duplexActiveLength(pair, step, springs, tippt)` takes TIPPT and rounds it
// to one decimal, because the reference computes from the figure it shows.
// dev/tippt-rounding.mjs then showed:
//
//   same tenth as the reference      524 readings   11.3% failing
//   a DIFFERENT tenth                175 readings   35.4% failing
//   of those, 2+ tenths out           42 readings   81.0% failing
//
// and the 42 are ALL hi-lift (D800-120, 525-54HL), 39 of 42 LOW, with the
// relative error correlating -0.937 with TURNS.
//
// tippt = weight * rEff / turns, so a turns error inverts straight into it.
// The corpus carries `referenceTurns` - the reference's OWN figure - so this
// can be checked directly instead of inferred. Standard lift is the control:
// if the error is confined to hi-lift, HILIFT_RADIUS_SCALE or the hi-lift
// turns geometry is where it lives.
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
    if (!(r.referenceTurns > 0) || !(r.referenceIppt > 0)) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const step = c.duplexStep;

    if (!step) continue;

    // Same pair on both sides, or their figures describe a different spring.
    if (`${step.outerWire}/${step.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const st = r.state;
    const ourTurns = c.turnsExact;
    const ourTippt = c.duplexTipptExact;

    if (!(ourTurns > 0) || !(ourTippt > 0)) continue;

    rows.push({
        hi: st.liftType === "Hi-Lift",
        hiIn: Number(st.liftin || 0),
        drum: String(st.drum || "").split(" ").pop(),
        height: Number(st.doorHeightFeet) * 12 + Number(st.doorHeightInches || 0),
        springs: c.duplexSpringCount,
        ourTurns, theirTurns: r.referenceTurns,
        turnsRel: ourTurns / r.referenceTurns - 1,
        ipptRel: ourTippt / r.referenceIppt - 1,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

const q = (xs, p) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.min(s.length - 1, Math.floor(s.length * p))] : NaN;
};
const show = (label, set, pick) => {
    if (set.length < 8) return;

    const xs = set.map(pick);
    const abs = xs.map(Math.abs);

    console.log(`  ${label.padEnd(26)}n=${String(set.length).padStart(4)}  `
        + `p10 ${(q(xs, .1) * 100).toFixed(4).padStart(9)}%  `
        + `median ${(q(xs, .5) * 100).toFixed(4).padStart(9)}%  `
        + `p90 ${(q(xs, .9) * 100).toFixed(4).padStart(9)}%  `
        + `max|.| ${(Math.max(...abs) * 100).toFixed(3)}%`);
};

console.log(`${rows.length} readings carrying BOTH the reference's turns and `
    + `its ippt, wire matching\n`);

console.log("1. OUR TURNS vs THE REFERENCE'S OWN TURNS\n");
show("ALL", rows, (x) => x.turnsRel);
show("Standard lift", rows.filter((x) => !x.hi), (x) => x.turnsRel);
show("HI-LIFT", rows.filter((x) => x.hi), (x) => x.turnsRel);
console.log("");
for (const d of [...new Set(rows.map((x) => x.drum))]) {
    show(`  drum ${d}`, rows.filter((x) => x.drum === d), (x) => x.turnsRel);
}

console.log("\n2. OUR TIPPT vs THEIRS, the same cuts\n");
show("ALL", rows, (x) => x.ipptRel);
show("Standard lift", rows.filter((x) => !x.hi), (x) => x.ipptRel);
show("HI-LIFT", rows.filter((x) => x.hi), (x) => x.ipptRel);

console.log("\n3. DOES THE TURNS ERROR EXPLAIN THE TIPPT ERROR?\n");
const hi = rows.filter((x) => x.hi);
const corr = (set, f, g) => {
    const xs = set.map(f), ys = set.map(g);
    const mx = xs.reduce((a, b) => a + b, 0) / xs.length;
    const my = ys.reduce((a, b) => a + b, 0) / ys.length;
    let n = 0, dx = 0, dy = 0;

    for (let i = 0; i < xs.length; i++) {
        n += (xs[i] - mx) * (ys[i] - my);
        dx += (xs[i] - mx) ** 2;
        dy += (ys[i] - my) ** 2;
    }

    return n / Math.sqrt(dx * dy || 1);
};

if (hi.length > 8) {
    console.log(`  hi-lift: corr(turns error, ippt error) = `
        + `${corr(hi, (x) => x.turnsRel, (x) => x.ipptRel).toFixed(3)}`);
    console.log(`           corr(turns error, our turns)   = `
        + `${corr(hi, (x) => x.turnsRel, (x) => x.ourTurns).toFixed(3)}`);
    console.log(`           corr(turns error, hi-lift in)  = `
        + `${corr(hi, (x) => x.turnsRel, (x) => x.hiIn).toFixed(3)}`);
    console.log(`           corr(turns error, door height) = `
        + `${corr(hi, (x) => x.turnsRel, (x) => x.height).toFixed(3)}`);
}

console.log("\n  tippt = weight * rEff / turns, so a turns error of -x% shows");
console.log("  up as a tippt error of about +x%. A STRONG NEGATIVE correlation");
console.log("  between the two is the signature of the turns being the cause.");
console.log("  If the turns error is flat and tiny while tippt drifts, the");
console.log("  fault is in rEff instead - HILIFT_RADIUS_SCALE is the suspect.");
