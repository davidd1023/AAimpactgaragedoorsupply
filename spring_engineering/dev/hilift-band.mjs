// THE HI-LIFT POLE BAND, SCORED ON SINGLE.
//
//   node dev/hilift-band.mjs [eval-single*.json ...]
//
// WHAT THIS IS FOR. 2026-11-13 traced a duplex length failure to its root
// cause for the first time (CLAUDE.md, "A COMPLETE CAUSAL CHAIN"): on drum
// D800-120 with hi-lift more than about 1.1x the door height, `turnsExact`
// divides by a MULTIPLIER that is approaching zero, and the fitted surface is
// least accurate exactly there. 13 of 699 duplex readings carry a turns error
// up to 9.18%; 0 of 418 below that ratio carry one at all.
//
// `turnsExact` IS SHARED WITH SINGLE, so the same band must be hypersensitive
// there - and Single is the only assembly the business sells. Single measures
// 99.9% over 1,246 clean readings, but those draws were residential doors,
// mostly standard lift. THE QUESTION IS WHETHER THE BAND WAS EVER SAMPLED,
// and this tool answers it from data already on disk before any request is
// spent.
//
// THE RATIO IS THE AXIS, NOT THE HI-LIFT AMOUNT. `single-breakdown.mjs`
// already slices by hi-lift inches, and that cut CANNOT SEE this: 105" of
// hi-lift on a 227" door is ratio 0.46 and perfectly safe, while the same
// 105" on an 84" door is ratio 1.25 and sits in the pole. The two readings
// land in the same bucket there and in opposite buckets here.
//
// THE EXTRACTION IS COPIED FROM `single-breakdown.mjs` ON PURPOSE. Three
// diagnostics in this repository have reported findings off invented field
// names (`i.springId`, `c.singleWireSize`, `duplexCycles` returning a
// formatted string); the rule written down after the third is that a tool
// measuring what another tool already reports must agree with it first.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { REF_RADIUS } from "./ref-state.mjs";

const mod = await load();

const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};
const files = process.argv.slice(2);

if (!files.length) {
    console.error("usage: node dev/hilift-band.mjs <eval-single*.json ...>");
    process.exit(1);
}

const rows = [];

for (const file of files) {
    let data;

    try {
        data = JSON.parse(readFileSync(file, "utf8"));
    } catch {
        console.error(`skipping ${file} - unreadable`);
        continue;
    }

    for (const r of data) {
        const i = r.input, d = r.data;
        const sp = d?.outerSpring || d?.innerSpring;

        if (r.error || !sp?.wireSize || !sp.springLength || !i?.innerDiameter) continue;
        if (i.assembly !== "Single") continue;

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";

        if (!hi) continue;                       // standard lift has no pole

        const idText = ID_TEXT[Number(i.innerDiameter)];

        if (!idText) continue;

        const c = make(mod, {
            assembly: "Single", drum: i.drum, springId: idText,
            springs: i.springs ?? 2,
            radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            liftType: "Hi-Lift", liftin: String(i.hiLift),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
            doorWidthInches: (i.widthInches ?? 108) % 12,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const ourWire = c.recommendedWire;
        const wireOk = ourWire !== null && Math.abs(ourWire - sp.wireSize) < 1e-9;

        // The multiplier and the turns, BEFORE the reference's wire is fed
        // back - neither depends on the wire, and both are what the pole
        // actually moves. `referenceMultiplier` / `turnsOnSprings` are only
        // present on pulls taken after import.mjs started keeping them.
        const ourMult = c.multiplierExact;
        const ourTurns = c.turnsExact;
        const refMult = d?.multiplier;
        const refTurns = d?.turnsOnSprings;

        c.state.wireSize = `${sp.wireSize}"`;

        const dLen = c.springLength - sp.springLength;
        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(String(m)));

        rows.push({
            clean: msgs.length === 0 && r.status === "success",
            wireOk, exact: dLen === 0, dLen,
            weightOk: Math.abs(c.springWeight - sp.springWeight) < 0.02,
            drum: (i.drum || "?").split(" ").pop(),
            height: i.heightInches, hiLift: i.hiLift,
            ratio: i.hiLift / i.heightInches,
            springs: i.springs ?? 2, weight: i.weight, id: Number(i.innerDiameter),
            ourMult, refMult, ourTurns, refTurns,
            turnsErr: refTurns ? (ourTurns - refTurns) / refTurns : null,
        });
    }
}

const pct = (a, b) => (b ? `${(100 * a / b).toFixed(1)}%` : "  -  ");
const clean = rows.filter((r) => r.clean);

console.log("=".repeat(78));
console.log(`HI-LIFT SINGLE - ${rows.length} readings, ${clean.length} clean`);
console.log("=".repeat(78));

const BANDS = [
    ["ratio < 0.6", (r) => r.ratio < 0.6],
    ["0.6 - 0.9", (r) => r.ratio >= 0.6 && r.ratio < 0.9],
    ["0.9 - 1.1", (r) => r.ratio >= 0.9 && r.ratio <= 1.1],
    ["OVER 1.1  (the pole)", (r) => r.ratio > 1.1],
];

function table(title, rs) {
    console.log(`\n${title}`);
    console.log("    band                      n    wire   length  weight");

    for (const [name, f] of BANDS) {
        const v = rs.filter(f);

        console.log(`    ${name.padEnd(22)}${String(v.length).padStart(5)}  `
            + `${pct(v.filter((x) => x.wireOk).length, v.length).padStart(6)}  `
            + `${pct(v.filter((x) => x.exact).length, v.length).padStart(6)}  `
            + `${pct(v.filter((x) => x.weightOk).length, v.length).padStart(6)}`);
    }
}

table("EVERY HI-LIFT DRUM", clean);

for (const drum of [...new Set(clean.map((r) => r.drum))].sort()) {
    table(`drum ${drum}`, clean.filter((r) => r.drum === drum));
}

// NAME THE BAND'S READINGS ONE BY ONE. A percentage over five readings tells
// nobody anything; the only two findings this project has ever shipped came
// from printing a concrete case.
const band = rows.filter((r) => r.ratio > 1.1);

console.log(`\nEVERY READING PAST 1.1 (${band.length}), clean or not:`);
console.log("    drum        height  hiLift  ratio  spr   weight  wire  len  "
    + "ourTurns  refTurns  err");

for (const r of band.sort((a, b) => b.ratio - a.ratio)) {
    console.log(`    ${r.drum.padEnd(10)}${String(r.height).padStart(6)}`
        + `${String(r.hiLift).padStart(8)}${r.ratio.toFixed(2).padStart(7)}`
        + `${String(r.springs).padStart(5)}${String(r.weight).padStart(8)}`
        + `${(r.wireOk ? "ok" : "MISS").padStart(6)}`
        + `${(r.exact ? "ok" : r.dLen.toFixed(2)).padStart(6)}  `
        + `${(r.ourTurns ?? 0).toFixed(2).padStart(8)}  `
        + `${r.refTurns === undefined ? "       -" : r.refTurns.toFixed(2).padStart(8)}  `
        + `${r.turnsErr === null ? "    -" : `${(100 * r.turnsErr).toFixed(2)}%`.padStart(7)}`
        + `${r.clean ? "" : "   (flagged)"}`);
}

// THE MULTIPLIER IS THE QUANTITY THAT ACTUALLY GOES NEAR ZERO. Printing its
// size per band is what turns "accuracy fell here" into "the denominator is
// twenty times smaller here", which is the finding that was made on duplex.
console.log("\n|multiplier| by band (the denominator turns divides by):");

for (const [name, f] of BANDS) {
    const v = clean.filter(f).map((r) => Math.abs(r.ourMult)).sort((a, b) => a - b);

    if (!v.length) continue;

    const q = (p) => v[Math.min(v.length - 1, Math.floor(p * v.length))];

    console.log(`    ${name.padEnd(22)}${String(v.length).padStart(5)}  `
        + `p10 ${q(0.1).toExponential(2)}  median ${q(0.5).toExponential(2)}  `
        + `p90 ${q(0.9).toExponential(2)}`);
}
