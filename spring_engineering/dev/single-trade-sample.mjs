// DRAW THE SINGLE DOORS THE SHOP ACTUALLY SELLS.
//
//   node dev/single-trade-sample.mjs <out.json> <seed> [count]
//
// THE REAL GAP, AND IT IS NOT ACCURACY. Duplex holds 10,172 clean reference
// readings; Single holds 342 - and Single is the only assembly the business
// sells (duplex is calculated but not manufactured, see CLAUDE.md). The
// percentages are perfect so far, on a twenty-ninth of the evidence. That
// imbalance is worth more than another decimal on duplex.
//
// WHY NOT dev/single-gap-sample.mjs. That one aims at the SLICES NOBODY HAD
// MEASURED - hi-lift, 12 ft and up, the two drums never drawn - which is the
// right shape for finding a blind spot and the wrong shape for measuring the
// everyday quote. It also yields badly: 67 clean of 249, because tall heavy
// multi-spring doors overrun the reference's own envelope.
//
// THIS DRAWS ORDINARY TRADE DOORS, so nearly all of them should come back
// clean, and it measures where the money is.
//
// FOUR THINGS KEEP THE YIELD UP, each from a documented failure:
//
//  - THE DRUM IS PICKED BY THE REFERENCE'S OWN RULE (learned 2026-11-11:
//    first drum in order whose maxHeight and maxWeight both clear the door).
//    Drawing a drum at random is how the earlier batches earnt
//    "exceeds the drum's capacity".
//  - WEIGHT COMES FROM THE DOOR'S AREA at a real lb/sqft, not from a flat
//    range - a 8x7 door and a 20x14 door do not weigh the same, and a weight
//    that does not match the door is the commonest way to leave the envelope.
//  - WIDTH IS A REAL DOOR WIDTH and the assembly must fit across it. "Torsion
//    assembly will be too long for a NNN" wide door" was 147 of the 249
//    rejections last time.
//  - ONLY THE THREE SOLD I.D.s. 1 3/4" and 4 3/8" are not offered to the
//    customer and 1 3/4" answers cleanly 7 times in 31.
//
// EVERY CASE IS STAMPED eval: true, so dev/derive.mjs can never fit it. These
// are a YARDSTICK - Single's length and weight are already exact and the open
// question is whether that holds across the trade, which only data the fitter
// has never seen can answer.
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { makeRnd } from "./rnd.mjs";
import { load } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, countArg] = process.argv.slice(2);

if (!out || !seedArg) {
    console.error("usage: node dev/single-trade-sample.mjs <out.json> <seed> [count]");
    console.error("");
    console.error("THE SEED IS REQUIRED - a sample nobody can redraw is not a yardstick.");
    process.exit(1);
}

// A pulled sample file holds ANSWERS, and this guard exists because a
// generator was once run at a path that already held an hour of polling.
if (existsSync(out) && !process.env.OVERWRITE) {
    console.error(`${out} already exists - refusing to overwrite it.`);
    console.error("Pick a new path, or set OVERWRITE=1 if you are certain it is only inputs.");
    process.exit(1);
}

const COUNT = Number(countArg) || 200;
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

// THE REFERENCE'S OWN DRUM RULE, in the order it applies them. Taken from the
// engine's table rather than typed out - the tooling has already been wrong
// twice by keeping its own copy (see CLAUDE.md).
const DRUM_ORDER = ["CANIMEX/TF D400-96", "CANIMEX/TF D400-144", "CANIMEX/TF D525-216"];
const pickDrum = (h, w) => DRUM_ORDER.find((n) => {
    const d = mod.DRUM_LIMITS[n];

    return d && d.maxHeight >= h && d.maxWeight >= w;
}) ?? null;

// Real door sizes, in inches. Residential runs 8-18 ft wide and 7-8 ft high;
// the taller and wider ones are light commercial.
const SIZES = [
    // [width, height, how often to draw it]
    [96, 84, 5], [108, 84, 3], [120, 84, 4], [144, 84, 4], [192, 84, 3],
    [96, 96, 3], [120, 96, 3], [144, 96, 4], [192, 96, 3], [216, 96, 2],
    [120, 108, 2], [144, 108, 3], [192, 108, 2],
    [144, 120, 3], [192, 120, 3], [216, 120, 2],
    [192, 144, 2], [216, 144, 2],
];
const SIZE_BAG = SIZES.flatMap(([w, h, n]) => Array(n).fill([w, h]));

// Pounds per square foot. A single-skin steel door is about 2; insulated
// sectional 3 to 4; a heavy commercial door more. Drawn as a range so the
// sample spans what walks in the door rather than one archetype.
const LB_PER_SQFT = [1.9, 4.6];

const IDS = [2.625, 3.75, 5.25];
// What the trade actually orders. 10,000 is the builder's standard and most
// of the book; the longer lives are specified rather than assumed.
const CYCLES = [10000, 10000, 10000, 15000, 25000, 25000, 50000, 100000];
const RADII = [15, 15, 15, 12, 10];

const { rnd, pick, between } = makeRnd(seedArg);
const cases = [];
const drawn = new Set();
let rejected = 0;

for (let k = 0; cases.length < COUNT && k < COUNT * 40; k++) {
    const [widthInches, heightInches] = pick(SIZE_BAG);
    const sqft = (widthInches / 12) * (heightInches / 12);
    const lbft = LB_PER_SQFT[0] + rnd() * (LB_PER_SQFT[1] - LB_PER_SQFT[0]);
    const weight = Math.round(sqft * lbft);

    const drum = pickDrum(heightInches, weight);

    if (!drum) { rejected++; continue; }   // heavier than any standard drum

    // A door nearly always carries a PAIR. One spring is a small light door
    // and three or four is heavy commercial, so the count follows the weight
    // rather than being drawn flat - a 4-spring 8 ft door is not a thing.
    const springs = weight < 150 ? pick([1, 1, 2])
        : weight < 400 ? pick([2, 2, 2, 1])
            : weight < 700 ? pick([2, 2, 4]) : pick([2, 4, 4]);

    const row = {
        label: `single-trade ${cases.length}`,
        garageDoorLineId: lineId,
        assembly: "Single",
        lift: "Standard",
        radius: pick(RADII),
        springs,
        innerDiameter: pick(IDS),
        drum,
        cycles: pick(CYCLES),
        widthInches,
        heightInches,
        weight,
        eval: true,
    };

    // NOT TWICE. A sampler that can emit the same case twice spends the
    // account on a question the reference has already answered.
    const key = [row.drum, row.springs, row.radius, row.cycles, row.weight,
        row.heightInches, row.widthInches, row.innerDiameter].join("|");

    if (drawn.has(key)) continue;

    drawn.add(key);
    cases.push(row);
}

// THE LAST GATE BEFORE THE ACCOUNT IS SPENT. It asserts the SWEEP, so it
// catches a repeat whatever caused it - the guard that would have caught the
// collapsed generator of batch V13 however it had happened.
const distinct = new Set(cases.map((c) => [c.drum, c.springs, c.radius, c.cycles,
    c.weight, c.heightInches, c.widthInches, c.innerDiameter].join("|")));

if (distinct.size !== cases.length) {
    console.error(`REFUSING TO WRITE ${out}: ${cases.length} cases but only `
        + `${distinct.size} distinct.`);
    process.exit(1);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} trade Single cases to ${out} (seed ${seedArg})`
    + `${rejected ? `, ${rejected} draws too heavy for a standard drum` : ""}`);

const tally = (name, f) => {
    const c = new Map();

    for (const r of cases) c.set(f(r), (c.get(f(r)) || 0) + 1);

    console.log(`  ${name}: ` + [...c].sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([k, v]) => `${k}:${v}`).join("  "));
};

tally("drum    ", (r) => r.drum.replace("CANIMEX/TF ", ""));
tally("springId", (r) => r.innerDiameter);
tally("springs ", (r) => r.springs);
tally("radius  ", (r) => r.radius);
tally("door    ", (r) => `${r.widthInches / 12}x${r.heightInches / 12}`);
console.log(`  weight  : ${Math.min(...cases.map((c) => c.weight))}`
    + ` to ${Math.max(...cases.map((c) => c.weight))} lb`);
