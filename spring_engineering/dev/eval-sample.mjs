// Draw a UNIFORM sample from the allowed parameter box, for measuring the
// model against data that has informed nothing.
//
//   node dev/eval-sample.mjs <out.json> <seed> <count>
//
// WHY THIS MATTERS MORE THAN IT LOOKS. The external samples this project
// quotes have had knobs tuned against them - LINE_SLACK twice, LEVEL_SUPPORT,
// SPLIT_MIN_SIDE - which makes them partly in-sample for those choices. A
// figure from a sample drawn after the tuning is the only one that is clean.
//
// NAME THE OUTPUT eval-rand-<something>.json. dev/derive.mjs skips any pull
// matching /(^|-)(eval|rand|biased)/, so a file named that way cannot
// accidentally be fitted - which has happened before and turned a reported
// 91.9% into a true 63.6%.
//
// Uniform means uniform over what a door can actually be: every drum, every
// radius, 1-4 springs, every cycle target, and height and weight uniform
// inside each drum's own rating rather than a shared range that would be out
// of bounds on the small drums and never reach the top of the large ones.
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, countArg] = process.argv.slice(2);

if (!out || !seedArg) {
    console.error("usage: node dev/eval-sample.mjs <out.json> <seed> <count>");
    console.error("");
    console.error("THE SEED IS REQUIRED. Without it the draw cannot be redrawn,");
    console.error("and a sample nobody can regenerate is not a yardstick.");
    process.exit(1);
}

// THIS SCRIPT WRITES INPUTS, AND A SAMPLE FILE HOLDS ANSWERS.
//
// Once a draw has been pulled, the file at this path is 380 readings off the
// reference that took an hour of polling at one request a second, and it is
// the only never-tuned yardstick this project has. Running the generator at it
// again replaces all of that with a fresh list of questions. Ask before it
// happens rather than after: it has happened once, and only a committed copy
// got it back.
if (existsSync(out) && !process.env.OVERWRITE) {
    console.error(`${out} already exists - refusing to overwrite it.`);
    console.error("");
    console.error("If it holds pulled readings, writing here destroys them. Pick a");
    console.error("new path, or set OVERWRITE=1 if you are certain it is only inputs.");
    process.exit(1);
}

const COUNT = Number(countArg) || 380;

let lineId = null;

for (const f of readdirSync(HERE).filter((x) => /^sweeps.*\.json$/.test(x))) {
    const hit = JSON.parse(readFileSync(join(HERE, f), "utf8")).find((c) => c.garageDoorLineId);

    if (hit) { lineId = hit.garageDoorLineId; break; }
}

if (!lineId) {
    console.error("no garageDoorLineId found in dev/sweeps*.json");
    process.exit(1);
}

// [name, max height, max weight, hi-lift, max hi-lift]
const DRUMS = [
    ["CANIMEX/TF D400-96", 96, 530, false, 0],
    ["CANIMEX/TF D400-144", 144, 750, false, 0],
    ["CANIMEX/TF D525-216", 231, 1500, false, 0],
    ["CANIMEX/TF 575-120", 192, 1000, true, 120],
    ["CANIMEX/TF 525-54HL", 234, 1000, true, 54],
    ["CANIMEX/TF D800-120", 384, 2200, true, 120],
];
const RADII = [10, 12, 15];
const CYCLES = [10000, 15000, 25000, 50000, 75000, 100000, 150000, 200000, 250000, 300000];

let seed = Number(seedArg) || 1;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const between = (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1));

const cases = [];

for (let k = 0; k < COUNT; k++) {
    const [drum, maxH, maxW, isHi, maxHiLift] = pick(DRUMS);
    const heightInches = between(84, Math.min(maxH, 240));
    const row = {
        label: `rand ${k}`, garageDoorLineId: lineId,
        assembly: "Duplex", lift: isHi ? "HiLift" : "Standard",
        radius: isHi ? 15 : pick(RADII),
        springs: between(1, 4), innerId: 3.75, outerId: 6, drum,
        cycles: pick(CYCLES), widthInches: 216, heightInches,
        weight: between(150, maxW),
    };

    if (isHi) {
        row.hiLift = between(12, maxHiLift);
    }

    cases.push(row);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} uniform cases to ${out} (seed ${seedArg})`);

const tally = (name, f) => {
    const c = new Map();

    for (const r of cases) c.set(f(r), (c.get(f(r)) || 0) + 1);

    console.log(`  ${name}: ` + [...c].sort((a, b) => b[1] - a[1])
        .map(([k, v]) => `${k}:${v}`).join("  "));
};

tally("drum   ", (r) => r.drum.replace("CANIMEX/TF ", ""));
tally("springs", (r) => r.springs);
tally("lift   ", (r) => r.lift);
