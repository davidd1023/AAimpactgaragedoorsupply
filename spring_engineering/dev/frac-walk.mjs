// Build a sweep that WALKS THE FRACTION of the active length.
//
//   node dev/frac-walk.mjs <out.json> <seed> <budget> '<group>' '<group>' ...
//   node dev/frac-walk.mjs dev/sweeps-F3.json 31337 380 '0.2625/0.2253|4' ...
//
// WHY THIS EXISTS. The quarter-inch bonus is a function of frac(active
// length), so the readings that settle it have to cover frac. A weight ladder
// does not: of 49 (rung, spring count) groups in the 1 lb bracket batch, 42
// held only whole lengths and could not see the rule at all. Walking frac
// instead found the rule on the first rung it was tried on - one threshold at
// 0.747 explaining all 60 readings.
//
// THREE THINGS IT GETS RIGHT, each of which was got wrong first:
//
//   ORDERABLE DOORS ONLY. The first version scanned weight upward and took the
//   first match, which on a big drum means a very light door - springs so
//   over-engineered the reference answered with 4.6 million cycles and a
//   warning. Flagged readings carry the least trustworthy lengths in the file,
//   so a candidate is only kept when our own warning set is EMPTY.
//
//   NOT THE FIRST CANDIDATE. Taking the first weight that matched tied the
//   bucket to the weight. It picks among all of a configuration's candidates
//   instead, so the two are uncorrelated.
//
//   ONE SAMPLE PER CONFIGURATION PER BUCKET. Dense readings from one drum,
//   height and target are a line through the input space, and folding such a
//   batch into the fit cost two points of accuracy. Every sample here comes
//   from an independently drawn configuration.
import { load, make } from "./harness.mjs";
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, budgetArg, ...groups] = process.argv.slice(2);

if (!out || !groups.length) {
    console.error("usage: node dev/frac-walk.mjs <out.json> <seed> <budget> '<rung>|<springs>' ...");
    process.exit(1);
}

const BUDGET = Number(budgetArg) || 340;
const TARGETS = new Set(groups);
const BUCKETS = 20;
const PER_BUCKET = 3;

// The account's line id, read from an existing sweep and never printed.
let lineId = null;

for (const f of readdirSync(HERE).filter((x) => /^sweeps.*\.json$/.test(x))) {
    const a = JSON.parse(readFileSync(join(HERE, f), "utf8"));
    const hit = a.find((c) => c.garageDoorLineId);

    if (hit) {
        lineId = hit.garageDoorLineId;
        break;
    }
}

if (!lineId) {
    console.error("no garageDoorLineId found in dev/sweeps*.json");
    process.exit(1);
}

// [name, max height, max weight, hi-lift?]
const DRUMS = [
    ["CANIMEX/TF D400-96", 96, 530, false],
    ["CANIMEX/TF D400-144", 144, 750, false],
    ["CANIMEX/TF D525-216", 231, 1500, false],
    ["CANIMEX/TF 575-120", 192, 1000, true],
    ["CANIMEX/TF 525-54HL", 234, 1000, true],
    ["CANIMEX/TF D800-120", 384, 2200, true],
];
const RADII = ["LHR", "12", "15"];
const CYCLES = ["10,000", "15,000", "25,000", "50,000", "100,000"];

let seed = Number(seedArg) || 1;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];

const mod = await load();
const counts = [...new Set([...TARGETS].map((g) => Number(g.split("|")[1])))];

// ONE PASS, THEN SELECT. The first version drew a configuration, scanned every
// weight for it, kept one reading and threw the rest away - so it re-did the
// same work thousands of times and took over ten minutes on the soft rungs,
// where most configurations never select a target rung at all.
//
// Now each configuration is scanned once and every orderable candidate it
// offers goes into a pool, which is then drawn from under the diversity rule.
// Same guarantees, a fraction of the work.
const pool = [];
let clean = 0, flagged = 0;

for (let draw = 0; draw < 900 && pool.length < 20000; draw++) {
    const [drum, maxH, maxW, isHi] = pick(DRUMS);
    const radius = isHi ? "15" : pick(RADII);
    const cycles = pick(CYCLES);
    const hIn = 84 + Math.floor(rnd() * (Math.min(maxH, 180) - 84));
    const springs = pick(counts);
    const liftIn = isHi ? String(12 + Math.floor(rnd() * 84)) : "";
    const cfg = `${drum}|${radius}|${cycles}|${hIn}|${springs}|${liftIn}`;
    let seenTarget = false, sinceTarget = 0;

    for (let w = 150; w <= Math.floor(maxW * 0.85); w += 4) {
        const c = make(mod, {
            assembly: "Duplex", drum, springId: '3 3/4" inside 6"', springs, radius, cycles,
            weight: String(w), doorWidthFeet: 18,
            ...(isHi ? { liftType: "Hi-Lift", liftin: liftIn } : {}),
            doorHeightFeet: Math.floor(hIn / 12), doorHeightInches: hIn % 12,
        });
        const s = c.duplexStep;

        if (!s) continue;

        const key = `${s.outerWire}/${s.innerWire}|${springs}`;

        if (!TARGETS.has(key)) {
            // Rungs stiffen as the door gets heavier, so once the targets are
            // behind us there is nothing left to find on this configuration.
            if (seenTarget && ++sinceTarget > 12) break;
            continue;
        }

        seenTarget = true;
        sinceTarget = 0;

        if ((c.warnings ?? []).length) { flagged++; continue; }

        const x = c.duplexActiveLength;

        if (!(x > 0) || x > 110) continue;

        clean++;
        pool.push({
            key, cfg, w, drum, radius, cycles, hIn, springs, isHi, liftIn,
            b: Math.min(BUCKETS - 1, Math.floor((x - Math.floor(x)) * BUCKETS)),
        });
    }
}

// Shuffle so selection is not biased by drum order, then take under the rule:
// at most PER_BUCKET per (group, bucket) and never the same configuration twice
// for the same bucket.
for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
}

const got = new Map(), usedCfg = new Map(), cases = [];

for (const p of pool) {
    if (cases.length >= BUDGET) break;

    const bk = `${p.key}|${p.b}`;

    if ((got.get(bk) || 0) >= PER_BUCKET) continue;
    if ((usedCfg.get(bk) || new Set()).has(p.cfg)) continue;

    got.set(bk, (got.get(bk) || 0) + 1);

    if (!usedCfg.has(bk)) usedCfg.set(bk, new Set());

    usedCfg.get(bk).add(p.cfg);
    cases.push({
        label: `frac ${p.key} b${p.b}`, garageDoorLineId: lineId,
        assembly: "Duplex", lift: p.isHi ? "HiLift" : "Standard",
        ...(p.isHi ? { hiLift: Number(p.liftIn) } : {}),
        radius: p.radius === "LHR" ? 10 : Number(p.radius), springs: p.springs,
        innerId: 3.75, outerId: 6, drum: p.drum, cycles: Number(p.cycles.replace(/,/g, "")),
        widthInches: 216, heightInches: p.hIn, weight: p.w,
    });
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} cases to ${out}  (clean candidates ${clean}, flagged rejected ${flagged})`);
console.log("\ngroup                 readings   frac buckets of 20");

const byGroup = new Map();

for (const [bk, n] of got) {
    const g = bk.split("|").slice(0, 2).join("|");
    byGroup.set(g, (byGroup.get(g) || 0) + n);
}

for (const g of groups) {
    const n = byGroup.get(g) || 0;
    const covered = [...got.keys()].filter((k) => k.startsWith(g + "|")).length;
    console.log(`${g.padEnd(22)} ${String(n).padStart(5)}        ${covered}${covered < 10 ? "   <- thin, may not be reachable on these drums" : ""}`);
}
