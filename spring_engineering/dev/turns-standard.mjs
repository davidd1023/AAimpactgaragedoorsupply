// STANDARD LIFT: OUR TURNS AND TIPPT AGAINST THE REFERENCE'S OWN FIGURES.
//
//   node dev/turns-standard.mjs
//
// WHY THIS EXISTS. `dev/turns-hilift.mjs` chased the hi-lift pole and carried
// standard lift only as a CONTROL - on the 54 readings the corpus happens to
// hold `referenceTurns` for. Standard lift is very nearly everything the
// business sells, and it had never been scored on more than those 54.
//
// IT CAN BE SCORED ON FAR MORE, because `turnsOnSprings` and
// `totalInchPoundPerTurn` ride on every raw pull and eval file, not only on
// the corpus rows that carry `referenceTurns`. That is 4,307 standard-lift
// readings against 54 - eighty times the evidence, already paid for.
//
// WHAT IT FOUND, and the reason nothing was changed:
//
//   TURNS   median +0.138%, p90 +0.501%, worst 0.878%  - and the median
//           tracks the TRACK RADIUS: -0.038% at r10, +0.103% at r12,
//           +0.294% at r15. Only 14.7% land within the reference's own
//           reporting step of 0.01, so this is a real difference and not
//           rounding.
//
//   TIPPT   median +0.0014%, p90 +0.039%, worst 0.187%, and FLAT in radius.
//
// **THE TURNS DIFFERENCE NEVER REACHES TIPPT**, which is what the length is
// built from - so length, weight and price are untouched by it. Our rEff and
// our turns are evidently fitted jointly, with only their RATIO pinned by the
// data, so the error cancels in `weight * rEff / turns`. That is the same
// shape as the `b` slope absorbing a stiffness scale error (CLAUDE.md): a
// parameter pair where one combination is determined and the other is free.
//
// SO THE ONLY THING CARRYING IT IS THE TURNS FIGURE ON SCREEN, out by under
// 0.05 of a turn on a typical 8.6 - well inside the quarter turn an installer
// actually adjusts by. Correcting it would mean moving rEff too, and rEff
// feeds the tippt that everything depends on. **Not worth it; measured so
// that nobody has to wonder.**
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { REF_RADIUS } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();

// The spelling the dropdown can actually produce - see single-breakdown.mjs.
const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};
const rows = [];

for (const f of readdirSync(HERE).filter((x) => /^(eval-|pulled-)/.test(x) && x.endsWith(".json"))) {
    let data;

    try {
        data = JSON.parse(readFileSync(join(HERE, f), "utf8"));
    } catch {
        continue;
    }

    if (!Array.isArray(data)) continue;

    for (const r of data) {
        const i = r.input, d = r.data;

        if (!i || !d || !d.turnsOnSprings || !d.totalInchPoundPerTurn) continue;
        // STANDARD LIFT ONLY. A hi-lift drum divides by a multiplier and has
        // its own tool; mixing them hides both.
        if (i.lift && i.lift !== "Standard") continue;

        const single = i.assembly === "Single";

        if (single && !ID_TEXT[Number(i.innerDiameter)]) continue;

        const c = make(mod, {
            assembly: i.assembly,
            drum: i.drum,
            springId: single ? ID_TEXT[Number(i.innerDiameter)] : '3 3/4" inside 6"',
            springs: i.springs ?? 2,
            radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 144) / 12),
            doorWidthInches: (i.widthInches ?? 144) % 12,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        // READ THE GETTER FOR THE ASSEMBLY IN PLAY. Asking a Single component
        // for a duplex figure returns a perfectly good number about a
        // different question - the fourth mistake of that family in this
        // repository, and the worst, because nothing about it looks wrong.
        const ourTippt = single
            ? (c.singleTipptExact ?? c.tipptExact)
            : c.duplexTipptExact;

        if (!Number.isFinite(ourTippt) || !Number.isFinite(c.turnsExact)) continue;

        rows.push({
            turns: (c.turnsExact - d.turnsOnSprings) / d.turnsOnSprings,
            absTurns: c.turnsExact - d.turnsOnSprings,
            tippt: (ourTippt - d.totalInchPoundPerTurn) / d.totalInchPoundPerTurn,
            radius: Number(i.radius),
            drum: (i.drum || "?").split(" ").pop(),
            assembly: i.assembly,
        });
    }
}

const q = (s, p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];

function stat(name, values) {
    if (!values.length) return;

    const s = values.slice().sort((a, b) => a - b);

    console.log(`  ${name.padEnd(22)}${`n=${s.length}`.padStart(7)}`
        + `  median ${(100 * q(s, 0.5)).toFixed(4).padStart(9)}%`
        + `  p90 ${(100 * q(s, 0.9)).toFixed(4).padStart(9)}%`
        + `  max|.| ${(100 * Math.max(...s.map(Math.abs))).toFixed(3)}%`);
}

console.log(`STANDARD LIFT - ${rows.length} readings carrying the reference's`
    + " own turns and ippt");

console.log("\n1. TURNS");
stat("all", rows.map((r) => r.turns));

for (const r of [10, 12, 15]) {
    stat(`radius ${r}`, rows.filter((x) => x.radius === r).map((x) => x.turns));
}

for (const d of [...new Set(rows.map((r) => r.drum))].sort()) {
    stat(`drum ${d}`, rows.filter((x) => x.drum === d).map((x) => x.turns));
}

// THE DISCRIMINATOR. The reference reports turns to 0.01, so matching it
// exactly would put nearly everything inside half a step. It does not.
const abs = rows.map((r) => Math.abs(r.absTurns));

console.log(`\n  within 0.005 of their figure (half a reported step): `
    + `${(100 * abs.filter((x) => x <= 0.005).length / abs.length).toFixed(1)}%`);
console.log(`  within 0.01                                        : `
    + `${(100 * abs.filter((x) => x <= 0.01).length / abs.length).toFixed(1)}%`);
console.log(`  worst absolute difference                          : `
    + `${Math.max(...abs).toFixed(4)} of a turn`);

console.log("\n2. TIPPT  <- what the LENGTH is built from");
stat("all", rows.map((r) => r.tippt));

for (const r of [10, 12, 15]) {
    stat(`radius ${r}`, rows.filter((x) => x.radius === r).map((x) => x.tippt));
}

console.log("\n  TIPPT IS FLAT IN RADIUS WHERE TURNS IS NOT. The turns error");
console.log("  cancels in weight * rEff / turns, so length and price never");
console.log("  see it. Only the turns figure on screen carries it, by under");
console.log("  0.05 of a turn. See this file's header before changing rEff.");
