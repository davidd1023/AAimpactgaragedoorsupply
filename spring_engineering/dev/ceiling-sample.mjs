// DRAW DOORS ABOVE THE DRUM CATALOGUE'S PUBLISHED CEILING.
//
//   node dev/ceiling-sample.mjs <sweeps-out.json> <seed> [count]
//
// THE ONE NAMED BLIND SPOT LEFT. `HL800_COLUMNS` carries, per hi-lift column,
// the catalogue's lowest AND highest published door height, and `hl800Base`
// reads neither - they are documentation nothing consults. The FLOOR turned
// out to be the hi-lift pole and shipped a guard (CLAUDE.md, 2026-11-13). The
// CEILING has never been measured against the reference at all: **zero
// readings above it, ever.**
//
//     hiLift      0   12   24   36   48   60   72   84   96  108  120
//     published  22   23   24   25   26   27   28   29   30   31   32  ft
//     engine     32   32   32   32   32   32   32   32   32   32   32  ft
//
// So at low hi-lift there is up to TEN FEET of door above the last published
// row, and the engine clamps only at the drum's 384" maxHeight.
//
// THE ARGUMENT SAYS IT IS SAFE, WHICH IS EXACTLY WHY IT IS WORTH ASKING. The
// columns are polynomials in `10/H`: extrapolating to a TALLER door sends
// `10/H` toward zero and the high-order terms vanish, where extrapolating
// below the floor sends it up and they run away. Measured on the engine at
// 12" of hi-lift the multiplier declines smoothly 0.404 -> 0.273 from 21 to
// 32 ft. **But that is our own engine agreeing with itself**, which is not
// evidence about the reference, and this file records several occasions where
// a sound argument was right and the measurement was still worth its cost.
//
// THE CONTROL IS NOT OPTIONAL. Half the draw sits BELOW the ceiling at the
// same hi-lift and the same weights, because a tall door is an awkward door
// for several reasons at once - the assembly has to fit the width, the spring
// runs long - and without a control a poor result reads as "tall doors are
// hard" rather than as the ceiling.
//
// WHAT TO SCORE. Not the length: these doors are far outside the reference's
// own 120" spring limit and it will flag nearly all of them. Score TURNS
// against `turnsOnSprings`, which the reference reports whether or not it
// stands behind the length - the same comparison that found the pole, and the
// reason that one worked on flagged readings.
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { makeRnd } from "./rnd.mjs";
import { load } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, countArg] = process.argv.slice(2);

if (!out || !seedArg) {
    console.error("usage: node dev/ceiling-sample.mjs <sweeps-out.json> <seed> [count]");
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

// THE PUBLISHED CEILING, READ OUT OF THE ENGINE'S OWN SOURCE rather than
// retyped. A fourth copy of a fact is a fourth chance to be wrong in one
// place only - this repository has recorded that three times (rnd.mjs,
// ref-state.mjs, the drum tables in two samplers).
const src = readFileSync(join(HERE, "..", "static/src/js/spring_engineering.js"), "utf8");
const block = src.split("const HL800_COLUMNS")[1].split("];")[0];
const columns = [...block.matchAll(/\[\s*(\d+),\s*([\d.]+),\s*([\d.]+),/g)]
    .map((m) => ({ hiLift: +m[1], loFt: +m[2], hiFt: +m[3] }));

if (columns.length < 10) {
    console.error(`parsed only ${columns.length} HL800 columns - the table's shape has changed`);
    process.exit(1);
}

const DRUM = "CANIMEX/TF D800-120";
const lim = mod.HILIFT_DRUMS[DRUM];
// Only the columns with real headroom above them are worth drawing: at 120"
// of hi-lift the published ceiling IS the drum's own 32 ft limit, so there is
// nothing above it to ask about.
const USABLE = columns.filter((c) => c.hiLift >= 12 && c.hiFt * 12 < lim.maxHeight - 12);

const IDS = [2.625, 3.75, 5.25];
const CYCLES = [10000, 10000, 25000, 50000];
const WIDTHS = [144, 168, 192, 216];
// Pounds per square foot, as dev/single-trade-sample.mjs uses - a weight that
// does not match the door is the commonest way to leave the envelope.
const LB_PER_SQFT = [1.9, 4.6];

const { rnd, pick } = makeRnd(seedArg);
const cases = [];
const drawn = new Set();
const want = { above: Math.round(COUNT / 2), below: COUNT - Math.round(COUNT / 2) };
let rejected = 0;

for (let k = 0; cases.length < COUNT && k < COUNT * 400; k++) {
    const band = want.above > 0 ? "above" : "below";
    const col = pick(USABLE);
    const ceilingIn = col.hiFt * 12;

    // ABOVE: between the published ceiling and the drum's own maxHeight.
    // BELOW: a comparable span under it, so the control is near the boundary
    // rather than drawn from short doors that share nothing with the band.
    const heightInches = band === "above"
        ? Math.round(ceilingIn + 6 + rnd() * (lim.maxHeight - ceilingIn - 6))
        : Math.round(ceilingIn - 6 - rnd() * 72);

    if (heightInches < 72 || heightInches > lim.maxHeight) { rejected++; continue; }

    const widthInches = pick(WIDTHS);
    const sqft = (widthInches / 12) * (heightInches / 12);
    const weight = Math.round(sqft * (LB_PER_SQFT[0]
        + rnd() * (LB_PER_SQFT[1] - LB_PER_SQFT[0])));

    if (weight > lim.maxWeight) { rejected++; continue; }

    const springs = weight < 400 ? pick([2, 2, 1]) : weight < 900 ? pick([2, 2, 4]) : pick([2, 4, 4]);

    const row = {
        label: `ceiling ${band} ${cases.length}`,
        garageDoorLineId: lineId,
        assembly: "Single",
        lift: "HiLift",
        radius: 15,
        springs,
        innerDiameter: pick(IDS),
        drum: DRUM,
        cycles: pick(CYCLES),
        widthInches,
        heightInches,
        weight,
        hiLift: col.hiLift,
        eval: true,
    };
    const key = [row.springs, row.cycles, row.weight, row.heightInches,
        row.widthInches, row.innerDiameter, row.hiLift].join("|");

    if (drawn.has(key)) continue;

    drawn.add(key);
    want[band] -= 1;
    cases.push(row);
}

const distinct = new Set(cases.map((c) => [c.springs, c.cycles, c.weight,
    c.heightInches, c.widthInches, c.innerDiameter, c.hiLift].join("|")));

if (distinct.size !== cases.length) {
    console.error(`REFUSING TO WRITE ${out}: ${cases.length} cases but only `
        + `${distinct.size} distinct.`);
    process.exit(1);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} ceiling cases to ${out} (seed ${seedArg})`
    + `${rejected ? `, ${rejected} draws outside the drum's range` : ""}`);
console.log(`  columns drawn from: ${USABLE.map((c) => `${c.hiLift}"(<=${c.hiFt}ft)`).join("  ")}`);

const tally = (name, f) => {
    const c = new Map();

    for (const r of cases) c.set(f(r), (c.get(f(r)) || 0) + 1);

    console.log(`  ${name}: ` + [...c].sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([k, v]) => `${k}:${v}`).join("  "));
};

tally("band    ", (r) => r.label.split(" ")[1]);
tally("hiLift  ", (r) => `${r.hiLift}"`);
tally("height  ", (r) => `${Math.floor(r.heightInches / 24) * 2}-${Math.floor(r.heightInches / 24) * 2 + 1}ft`);
console.log(`  weight  : ${Math.min(...cases.map((c) => c.weight))}`
    + ` to ${Math.max(...cases.map((c) => c.weight))} lb`);
