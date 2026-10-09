// Draw a SINGLE-assembly sample aimed at the two slices nobody has measured.
//
//   node dev/single-gap-sample.mjs <out.json> <seed> [count]
//
// WHY THIS IS NOT dev/eval-sample.mjs. That script draws uniformly over the
// whole box, which is the right shape for a figure to quote and the wrong
// shape for a gap. dev/eval-single.json is 292 readings and 181 clean ones,
// and the Single path scores 100% on every slice of it - but the slices are
// not the same size:
//
//     hi-lift                     13 readings, 6 clean, ONE drum, ONE spring ID
//     doors taller than 12 ft     33 readings
//     drums 525-54HL, D800-120    never drawn for Single at all
//
// "100% on 6 readings" and "100% on 58 readings" are the same number printed
// the same way, and only one of them means anything. A uniform redraw would
// spend most of its requests re-confirming the short standard-lift doors that
// are already saturated; this one spends them where the evidence is thin.
//
// THE DRAW IS STILL BLIND. Nothing here is chosen from how the model behaves -
// only from which inputs have been ASKED about. Stratifying on coverage keeps
// the sample honest; stratifying on error would not, and that mistake has
// already been made once in this repo with the boundary-dense pulls.
//
// EVERY CASE IS STAMPED eval: true, so dev/derive.mjs can never fit it and
// dev/pull.mjs refuses to write it anywhere the fitter reads.
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, countArg, hiShareArg] = process.argv.slice(2);

if (!out || !seedArg) {
    console.error("usage: node dev/single-gap-sample.mjs <out.json> <seed> [count] [hiShare]");
    console.error("");
    console.error("THE SEED IS REQUIRED - a sample nobody can redraw is not a yardstick.");
    process.exit(1);
}

// A pulled sample file holds ANSWERS. See dev/eval-sample.mjs - this guard is
// there because the generator was once run at a path that already held an
// hour of polling, and only a committed copy got it back.
if (existsSync(out) && !process.env.OVERWRITE) {
    console.error(`${out} already exists - refusing to overwrite it.`);
    console.error("Pick a new path, or set OVERWRITE=1 if you are certain it is only inputs.");
    process.exit(1);
}

const COUNT = Number(countArg) || 200;

let lineId = null;

for (const f of readdirSync(HERE).filter((x) => /^sweeps.*\.json$/.test(x))) {
    const hit = JSON.parse(readFileSync(join(HERE, f), "utf8")).find((c) => c.garageDoorLineId);

    if (hit) { lineId = hit.garageDoorLineId; break; }
}

if (!lineId) {
    console.error("no garageDoorLineId found in dev/sweeps*.json");
    process.exit(1);
}

// [name, max height, max weight, max hi-lift (0 = standard only)]
const DRUMS = [
    ["CANIMEX/TF D400-96", 96, 530, 0],
    ["CANIMEX/TF D400-144", 144, 750, 0],
    ["CANIMEX/TF D525-216", 231, 1500, 0],
    ["CANIMEX/TF 575-120", 192, 1000, 120],
    ["CANIMEX/TF 525-54HL", 234, 1000, 54],
    ["CANIMEX/TF D800-120", 384, 2200, 120],
];
const HI_DRUMS = DRUMS.filter((d) => d[3] > 0);
// A HI-LIFT DRUM ANSWERS ONLY UNDER HI-LIFT.
//
// The first run of this generator put 48 of its 200 requests into standard
// lift on 525-54HL, 575-120 and D800-120. Not one came back as JSON - the
// reference serves an HTML page for that combination, while the same three
// drums under HiLift answered 120 times out of 120. They are hi-lift drums;
// standard lift is not a configuration they have.
//
// A quarter of the draw spent on an impossible combination, and it read as a
// session expiry for an hour because HTML is also what a logged-out server
// returns. So the tall-door block takes only drums that do standard lift,
// which leaves D400-144 (to 144") and D525-216 (to 231") - and D525-216 alone
// above 12 ft.
const TALL_DRUMS = DRUMS.filter((d) => d[1] >= 144 && d[3] === 0);

// ONLY THE THREE SPRING IDS THE BUSINESS SELLS. See CLAUDE.md: "we are not
// using all of the single spring id's only the ones that are visible to the
// user". Drawing 1 3/4" and 4 3/8" would spend a fifth of the requests on
// sizes no customer can order - and 1 3/4" is the worst offender anyway, 7
// clean readings out of 31, because almost any real door drives its wire past
// the maximum.
//
// Each ID carries the PER-SPRING weight band that actually returns a spring
// rather than a wire-out-of-range error, read off the clean readings in
// dev/eval-single.json. Picking the weight from the ID instead of from the
// drum is what keeps the clean rate up: the error is nearly always wire
// min/max, and wire follows load per spring, not the drum's plate rating.
const IDS = [
    [2.625, 80, 230],
    [3.75, 110, 400],
    [5.25, 180, 600],
];
const RADII = [10, 12, 15];
const CYCLES = [10000, 15000, 25000, 50000, 75000, 100000, 150000, 200000, 250000, 300000];

let seed = Number(seedArg) || 1;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const between = (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1));

// 60/40 between the two gaps. Hi-lift is the thinner slice - 6 clean readings
// against 33 - and it is the one with a known history of hiding a wrong
// constant, so it gets the larger share.
// A top-up draw wants ONE of the two blocks, not both, so the split is an
// argument. It is still declared before the draw and never changed after
// seeing a result - a share chosen to chase a number would quietly turn this
// into a filtered sample.
const HI_SHARE = hiShareArg === undefined ? 0.6 : Number(hiShareArg);

if (!(HI_SHARE >= 0 && HI_SHARE <= 1)) {
    console.error(`hi-lift share must be between 0 and 1, got ${hiShareArg}`);
    process.exit(1);
}
const cases = [];

for (let k = 0; k < COUNT; k++) {
    const wantHi = k < Math.round(COUNT * HI_SHARE);
    const [drum, maxH, maxW, maxHi] = pick(wantHi ? HI_DRUMS : TALL_DRUMS);
    const [innerDiameter, loPer, hiPer] = pick(IDS);
    const springs = between(1, 4);

    // Weight from the ID's per-spring band, then clipped to the drum's own
    // rating - both limits are real and either one alone returns an error.
    const weight = Math.min(maxW, springs * between(loPer, hiPer));

    const row = {
        label: wantHi ? `single-hi ${k}` : `single-tall ${k}`,
        garageDoorLineId: lineId,
        assembly: "Single",
        lift: wantHi ? "HiLift" : "Standard",
        // Hi-lift is drawn at radius 15 only, matching dev/eval-sample.mjs.
        // The point of this draw is hi-lift AMOUNT crossed with drum, ID,
        // height and spring count; adding radius on top would thin every cell
        // for a factor that standard lift already measures at all three.
        radius: wantHi ? 15 : pick(RADII),
        springs,
        innerDiameter,
        drum,
        cycles: pick(CYCLES),
        // The widest door the box allows. The commonest non-wire error is
        // "torsion assembly will be too long for a NNN" wide door", and on a
        // tall door with four springs a narrow header throws it away before
        // the length can be compared at all.
        widthInches: 216,
        heightInches: wantHi
            ? between(84, Math.min(maxH, 240))
            // THE WHOLE POINT of this block: 12 ft and up, which
            // dev/eval-single.json has 33 readings of.
            : between(144, Math.min(maxH, 234)),
        weight,
        eval: true,
    };

    if (wantHi) {
        row.hiLift = between(12, maxHi);
    }

    cases.push(row);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} Single gap cases to ${out} (seed ${seedArg})`);

const tally = (name, f) => {
    const c = new Map();

    for (const r of cases) c.set(f(r), (c.get(f(r)) || 0) + 1);

    console.log(`  ${name}: ` + [...c].sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([k, v]) => `${k}:${v}`).join("  "));
};

tally("lift    ", (r) => r.lift);
tally("drum    ", (r) => r.drum.replace("CANIMEX/TF ", ""));
tally("springId", (r) => r.innerDiameter);
tally("springs ", (r) => r.springs);
tally("hiLift  ", (r) => (r.hiLift === undefined ? "-" : `${Math.floor(r.hiLift / 24) * 24}+`));
tally("height  ", (r) => `${Math.floor(r.heightInches / 24) * 24}+`);
