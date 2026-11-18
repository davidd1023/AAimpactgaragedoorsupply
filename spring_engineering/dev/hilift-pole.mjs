// THE HI-LIFT TURNS ERROR IS AMPLIFICATION AT A POLE, NOT A WRONG FORMULA.
//
//   node dev/hilift-pole.mjs
//
// HOW THIS WAS REACHED, because the chain matters more than the answer.
// A length failure was traced back through the only reading-specific input
// `duplexActiveLength` takes:
//
//   length  <- tippt (rounded to a tenth)      dev/tippt-rounding.mjs
//   tippt   <- weight * rEff / TURNS           corr(turns err, ippt err) -0.897
//   turns   <- rEff / MULTIPLIER   (hi-lift)   this file
//
// and `turnsExact` says in its own comment that the hi-lift branch is a
// division "which is what lets turns go to a pole where the multiplier
// crosses zero". So near that pole a tiny multiplier error is amplified
// without bound - which is exactly the shape measured:
//
//   13 of 699 readings have a turns error over 1%, up to 9.18%
//   ALL are drum D800-120, ALL have hiLift/height > 1.1
//   0 of 418 readings below that ratio are wrong
//
// THE TEST. The reference reports its OWN multiplier, so the quantity BEFORE
// the amplification can be compared directly. If our multiplier agrees to a
// hair and only the quotient diverges, nothing is wrong with the model and
// the band is simply ill-conditioned - which is a fact to record, not a bug
// to fix. If the multiplier itself is off, that IS fixable.
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
    if (!(r.referenceTurns > 0) || r.referenceMultiplier === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const step = c.duplexStep;

    if (!step) continue;
    if (`${step.outerWire}/${step.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) continue;

    const ourM = c.multiplierExact;
    const ourT = c.turnsExact;

    if (!(ourT > 0) || !Number.isFinite(ourM)) continue;

    const st = r.state;
    const h = Number(st.doorHeightFeet) * 12 + Number(st.doorHeightInches || 0);

    rows.push({
        hi: st.liftType === "Hi-Lift",
        ratio: h > 0 ? Number(st.liftin || 0) / h : 0,
        ourM, theirM: r.referenceMultiplier,
        mAbs: ourM - r.referenceMultiplier,
        mRel: r.referenceMultiplier ? ourM / r.referenceMultiplier - 1 : 0,
        turnsRel: ourT / r.referenceTurns - 1,
        ourT,
    });
}

const q = (xs, p) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.min(s.length - 1, Math.floor(s.length * p))] : NaN;
};

console.log(`${rows.length} readings carrying the reference's own MULTIPLIER\n`);
console.log("THE MULTIPLIER ITSELF - the quantity before the division\n");
console.log("  set                   n     median |err|   p90 |err|   max |err|"
    + "    (absolute)");

for (const [label, set] of [
    ["ALL", rows],
    ["turns error <= 1%", rows.filter((x) => Math.abs(x.turnsRel) <= 0.01)],
    ["turns error > 1%", rows.filter((x) => Math.abs(x.turnsRel) > 0.01)],
]) {
    if (set.length < 5) continue;

    const a = set.map((x) => Math.abs(x.mAbs));

    console.log(`  ${label.padEnd(20)}${String(set.length).padStart(5)}`
        + `${q(a, .5).toExponential(2).padStart(15)}`
        + `${q(a, .9).toExponential(2).padStart(12)}`
        + `${Math.max(...a).toExponential(2).padStart(12)}`);
}

console.log("\nAND HOW BIG THE MULTIPLIER IS - how near the pole each sits\n");
console.log("  set                   n     median |mult|    min |mult|");

for (const [label, set] of [
    ["turns error <= 1%", rows.filter((x) => Math.abs(x.turnsRel) <= 0.01)],
    ["turns error > 1%", rows.filter((x) => Math.abs(x.turnsRel) > 0.01)],
]) {
    if (set.length < 5) continue;

    const a = set.map((x) => Math.abs(x.theirM));

    console.log(`  ${label.padEnd(20)}${String(set.length).padStart(5)}`
        + `${q(a, .5).toExponential(2).padStart(16)}`
        + `${Math.min(...a).toExponential(2).padStart(14)}`);
}

// The decisive arithmetic: does the SAME tiny multiplier error account for
// the turns error, given how near the pole the reading sits?
console.log("\nIS THE TURNS ERROR JUST THAT MULTIPLIER ERROR, AMPLIFIED?\n");
console.log("  predicted turns error = -(multiplier error) / multiplier\n");
console.log("   |mult|     mult err    predicted   actual turns err");

for (const x of rows.filter((x) => Math.abs(x.turnsRel) > 0.01)
    .sort((a, b) => Math.abs(b.turnsRel) - Math.abs(a.turnsRel)).slice(0, 13)) {
    const predicted = -x.mAbs / x.theirM;

    console.log(`  ${Math.abs(x.theirM).toExponential(2).padStart(9)}`
        + `${x.mAbs.toExponential(2).padStart(13)}`
        + `${(predicted * 100).toFixed(2).padStart(11)}%`
        + `${(x.turnsRel * 100).toFixed(2).padStart(15)}%`);
}

console.log("\n  THE TWO COLUMNS MATCHING means the turns error is entirely the");
console.log("  multiplier error divided by a small number - amplification, not");
console.log("  a wrong formula. The multiplier would then have to be an order");
console.log("  of magnitude more accurate to fix these, and it is already the");
console.log("  most accurate quantity in the engine.");
