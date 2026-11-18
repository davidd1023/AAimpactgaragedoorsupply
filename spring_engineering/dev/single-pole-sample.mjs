// DRAW SINGLE DOORS ACROSS THE HI-LIFT POLE.
//
//   node dev/single-pole-sample.mjs <eval-out.json> <seed> [count]
//
// WHAT THE POLE IS. On a catalogue hi-lift drum the multiplier is a surface
// in (door height, hi-lift), and `turnsExact` DIVIDES by it. The drum's own
// catalogue publishes that surface only down to a lowest height per hi-lift
// column, and `HL800_COLUMNS` records it: the floor is exactly
// max(72", hiLift). So the moment the hi-lift exceeds the door's own height,
// the engine is extrapolating off the bottom of every column - and the
// multiplier runs to zero and through it.
//
// Measured on the installed engine, D800-120, no requests spent:
//
//     hiLift 96"   height 96"  ratio 1.00   mult  1.96e-1   turns     26.4
//                  height 84"  ratio 1.14   mult -3.38e-4   turns -15260.8
//                  height 72"  ratio 1.33   mult -3.65e-1   turns    -14.1
//
// 62.5% of configurations past ratio 1.0 return a NEGATIVE spring length,
// every one of them with no warning. (None is buyable: the wire that falls
// out of a nonsense turns figure is always one the shop does not stock, so
// `cannotBeSold` blocks it - by luck, not by design.)
//
// WHY A PULL IS STILL WORTH IT. Everything above is about OUR engine. Two
// things are unknown and only the reference can say:
//
//   1. Does the reference break there too? If it also extrapolates, there is
//      nothing to fit and the answer is a REFUSAL in the product, not a
//      better surface.
//   2. The strip just past the floor - ratio 1.0 to about 1.15 - returns a
//      PLAUSIBLE positive number (42 turns, a 30" spring). A believable wrong
//      answer is the dangerous kind, and nothing here can tell whether it is
//      wrong without asking.
//
// THE CONTROL IS NOT OPTIONAL. Roughly half of every draw sits at ratio 0.5
// to 0.9 on the same drums, same weights, same door sizes. Without it a poor
// yield in the band reads as "hi-lift doors are awkward" rather than as the
// pole, which is exactly the misreading the past-120" determinism check was
// built to prevent.
//
// EVERY CASE IS STAMPED eval: true - a yardstick, never training data - so
// the output path must carry "eval" in its name or dev/pull.mjs refuses it.
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { makeRnd } from "./rnd.mjs";
import { load } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, countArg] = process.argv.slice(2);

if (!out || !seedArg) {
    console.error("usage: node dev/single-pole-sample.mjs <eval-out.json> <seed> [count]");
    console.error("");
    console.error("THE SEED IS REQUIRED - a sample nobody can redraw is not a yardstick.");
    process.exit(1);
}

if (existsSync(out) && !process.env.OVERWRITE) {
    console.error(`${out} already exists - refusing to overwrite it.`);
    process.exit(1);
}

const COUNT = Number(countArg) || 40;
const mod = await load();

let lineId = null;

for (const f of readdirSync(HERE).filter((x) => /^sweeps.*\.json$/.test(x))) {
    const hit = JSON.parse(readFileSync(join(HERE, f), "utf8")).find((c) => c.garageDoorLineId);

    if (hit) { lineId = hit.garageDoorLineId; break; }
}

if (!lineId) {
    console.error("no garageDoorLineId found in dev/sweeps*.json");
    process.exit(1);
}

// Read the drums from the engine's own table. The tooling has kept its own
// copy of this twice and been wrong both times (CLAUDE.md); `525-54HL` is
// excluded because its 54" ceiling puts the pole below any real door.
const ALL_DRUMS = ["CANIMEX/TF D800-120", "CANIMEX/TF 575-120"];
// DRUM=D800-120 narrows the draw to one drum. The first probe found that only
// the D800-120 breaks - the 575-120's worst turns error in the band is 0.52%
// against the D800's 37% - so a follow-up has no reason to spend half its
// requests on the drum that works.
const DRUMS = process.env.DRUM
    ? ALL_DRUMS.filter((d) => d.includes(process.env.DRUM))
    : ALL_DRUMS;

if (!DRUMS.length) {
    console.error(`DRUM=${process.env.DRUM} matches none of: ${ALL_DRUMS.join(", ")}`);
    process.exit(1);
}

const limits = (n) => mod.HILIFT_DRUMS[n];

// Where each draw is aimed. The control is half the sample on purpose.
//
// RATIO=lo:hi aims the WHOLE draw at one strip instead, which is what the
// second probe needed: everything at or below the catalogue floor is clean
// and sellable, so "is the drum that breaks past the floor still right UP TO
// it" is the only band question a customer can actually reach.
const TARGETS = process.env.RATIO
    ? [["aimed", ...process.env.RATIO.split(":").map(Number)]]
    : [
        ["control", 0.50, 0.90],
        ["edge", 0.95, 1.15],
        ["past", 1.15, 1.60],
    ];
const PLAN = process.env.RATIO
    ? [["aimed", 1]]
    : [["control", 0.5], ["edge", 0.25], ["past", 0.25]];

// Door heights that can reach the band at all. The hi-lift ceiling is 120",
// so ratio 1.15 needs a door under 105" - these are ordinary heights, which
// is the point: the pole is reached by a SHORT door under a high ceiling,
// not by an exotic one.
const HEIGHTS = [72, 84, 90, 96, 108, 120, 132];
const WIDTHS = [96, 120, 144, 168, 192];
const LB_PER_SQFT = [1.9, 4.6];
const IDS = [2.625, 3.75, 5.25];
const CYCLES = [10000, 10000, 25000, 50000];

const { rnd, pick, between } = makeRnd(seedArg);
const cases = [];
const drawn = new Set();
const want = new Map(PLAN.map(([k, share]) => [k, Math.round(COUNT * share)]));
let rejected = 0;

for (let k = 0; cases.length < COUNT && k < COUNT * 400; k++) {
    const band = PLAN.map(([n]) => n).find((n) => (want.get(n) ?? 0) > 0);

    if (!band) break;

    const [, loR, hiR] = TARGETS.find((t) => t[0] === band);
    const drum = pick(DRUMS);
    const lim = limits(drum);
    const heightInches = pick(HEIGHTS);
    const ratio = loR + rnd() * (hiR - loR);
    const hiLift = Math.round(heightInches * ratio);

    // 12" is the engine's own floor (under it hi-lift behaves as zero) and
    // the drum's ceiling is a hard refusal, not a clamp - above it the
    // calculator falls back to the 0" column, which is a different question.
    if (hiLift < 12 || hiLift > lim.maxHiLift) { rejected++; continue; }
    if (heightInches > lim.maxHeight) { rejected++; continue; }

    const widthInches = pick(WIDTHS);
    const sqft = (widthInches / 12) * (heightInches / 12);
    const weight = Math.round(sqft * (LB_PER_SQFT[0]
        + rnd() * (LB_PER_SQFT[1] - LB_PER_SQFT[0])));

    if (weight > lim.maxWeight) { rejected++; continue; }

    const springs = weight < 150 ? pick([1, 1, 2])
        : weight < 400 ? pick([2, 2, 2, 1])
            : weight < 700 ? pick([2, 2, 4]) : pick([2, 4, 4]);

    const row = {
        label: `single-pole ${band} ${cases.length}`,
        garageDoorLineId: lineId,
        assembly: "Single",
        lift: "HiLift",
        radius: 15,                       // hi-lift forces 15 in the engine
        springs,
        innerDiameter: pick(IDS),
        drum,
        cycles: pick(CYCLES),
        widthInches,
        heightInches,
        weight,
        hiLift,
        eval: true,
    };

    const key = [row.drum, row.springs, row.cycles, row.weight,
        row.heightInches, row.widthInches, row.innerDiameter, row.hiLift].join("|");

    if (drawn.has(key)) continue;

    drawn.add(key);
    want.set(band, want.get(band) - 1);
    cases.push(row);
}

const distinct = new Set(cases.map((c) => [c.drum, c.springs, c.cycles, c.weight,
    c.heightInches, c.widthInches, c.innerDiameter, c.hiLift].join("|")));

if (distinct.size !== cases.length) {
    console.error(`REFUSING TO WRITE ${out}: ${cases.length} cases but only `
        + `${distinct.size} distinct.`);
    process.exit(1);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} hi-lift pole cases to ${out} (seed ${seedArg})`
    + `${rejected ? `, ${rejected} draws outside a drum's range` : ""}`);

const tally = (name, f) => {
    const c = new Map();

    for (const r of cases) c.set(f(r), (c.get(f(r)) || 0) + 1);

    console.log(`  ${name}: ` + [...c].sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([k, v]) => `${k}:${v}`).join("  "));
};

tally("band    ", (r) => r.label.split(" ")[1]);
tally("drum    ", (r) => r.drum.replace("CANIMEX/TF ", ""));
tally("ratio   ", (r) => (r.hiLift / r.heightInches).toFixed(1));
tally("height  ", (r) => `${r.heightInches}"`);
tally("springs ", (r) => r.springs);
console.log(`  weight  : ${Math.min(...cases.map((c) => c.weight))}`
    + ` to ${Math.max(...cases.map((c) => c.weight))} lb`);
