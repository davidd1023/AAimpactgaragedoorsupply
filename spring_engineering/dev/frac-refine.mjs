// Sample densely AT a group's fitted thresholds, to place them more precisely.
//
//   node dev/frac-refine.mjs <out.json> <seed> <budget> '<rung>|<springs>' ...
//
// WHY. dev/frac-walk.mjs covers frac in twentieths, which finds the SHAPE of a
// group's rule. What is left wrong after that is not shape but placement: of
// the ten clean misses when this was written, eight sat within 0.025 of a
// fitted threshold and six within 0.007. A reading that close is decided by
// where the boundary is to three decimal places, and a bucket 0.05 wide cannot
// say.
//
// So this reads the thresholds out of the SHIPPED table, works out where each
// one falls for the integer part a candidate lands on - they move with it - and
// keeps only candidates within WINDOW of one, bucketed at 0.0025. Everything
// else is the walk's recipe: orderable doors only, one sample per configuration
// per bucket, configurations drawn independently.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, budgetArg, ...groups] = process.argv.slice(2);

if (!out || !groups.length) {
    console.error("usage: node dev/frac-refine.mjs <out.json> <seed> <budget> '<rung>|<springs>' ...");
    process.exit(1);
}

const BUDGET = Number(budgetArg) || 340;
const TARGETS = new Set(groups);
const WINDOW = Number(process.env.WINDOW || 0.03);
const STEP = 0.0025;
const PER_BUCKET = 2;

let lineId = null;

for (const f of readdirSync(HERE).filter((x) => /^sweeps.*\.json$/.test(x))) {
    const hit = JSON.parse(readFileSync(join(HERE, f), "utf8")).find((c) => c.garageDoorLineId);

    if (hit) { lineId = hit.garageDoorLineId; break; }
}

if (!lineId) {
    console.error("no garageDoorLineId found in dev/sweeps*.json");
    process.exit(1);
}

const mod = await load();
const CAL = mod.DUPLEX_PAIRS['3 3/4" inside 6"'].calibration;

// Every threshold a group uses at a given integer part.
function thresholds(rung, springs, whole) {
    const step = CAL.find((p) => `${p.outerWire}/${p.innerWire}` === rung);

    if (!step) return [];

    const sp = step.splitByCount?.[springs];
    const line = sp ? (whole >= sp.from ? sp.above : sp.below) : step.lineByCount?.[springs];
    const ts = [];

    if (line) {
        ts.push(line.a + line.b * whole);

        if (line.a2 !== undefined) ts.push(line.a2 + (line.b2 ?? line.b) * whole);
        if (line.cuts) for (const c of line.cuts) ts.push(c + line.b * whole);
    } else if (step.byCount?.[springs]) {
        for (const b of step.byCount[springs]) if (b.upTo < 1) ts.push(b.upTo);
    }

    return ts.filter((t) => t > 0 && t < 1);
}

const DRUMS = [
    ["CANIMEX/TF D400-96", 96, 530, false],
    ["CANIMEX/TF D400-144", 144, 750, false],
    ["CANIMEX/TF D525-216", 231, 1500, false],
    ["CANIMEX/TF 575-120", 192, 1000, true],
    ["CANIMEX/TF 525-54HL", 234, 1000, true],
    ["CANIMEX/TF D800-120", 384, 2200, true],
];
const RADII = ["LHR", "12", "15"];
const CYCLES = ["10,000", "15,000", "25,000", "50,000", "100,000", "200,000"];

let seed = Number(seedArg) || 1;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const counts = [...new Set([...TARGETS].map((g) => Number(g.split("|")[1])))];
const pool = [];
let near = 0, far = 0;

for (let draw = 0; draw < 600; draw++) {
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

        const rung = `${s.outerWire}/${s.innerWire}`;
        const key = `${rung}|${springs}`;

        if (!TARGETS.has(key)) {
            if (seenTarget && ++sinceTarget > 12) break;
            continue;
        }

        seenTarget = true;
        sinceTarget = 0;

        if ((c.warnings ?? []).length) continue;

        const x = c.duplexActiveLength;

        if (!(x > 0) || x > 110) continue;

        const whole = Math.floor(x), frac = x - whole;
        const ts = thresholds(rung, springs, whole);

        if (!ts.length) continue;

        const d = Math.min(...ts.map((t) => Math.abs(frac - t)));

        if (d > WINDOW) { far++; continue; }

        near++;
        pool.push({ key, cfg, w, drum, radius, cycles, hIn, springs, isHi, liftIn,
                    b: Math.round(frac / STEP) });
    }
}

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
        label: `refine ${p.key}`, garageDoorLineId: lineId, assembly: "Duplex",
        lift: p.isHi ? "HiLift" : "Standard", ...(p.isHi ? { hiLift: Number(p.liftIn) } : {}),
        radius: p.radius === "LHR" ? 10 : Number(p.radius), springs: p.springs,
        innerId: 3.75, outerId: 6, drum: p.drum, cycles: Number(p.cycles.replace(/,/g, "")),
        widthInches: 216, heightInches: p.hIn, weight: p.w,
    });
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} cases  (within ${WINDOW} of a threshold: ${near}, discarded as far: ${far})`);

const byGroup = new Map();

for (const [bk, n] of got) {
    const g = bk.split("|").slice(0, 2).join("|");
    byGroup.set(g, (byGroup.get(g) || 0) + n);
}

console.log("\ngroup                 readings near a threshold");

for (const g of groups) console.log(`${g.padEnd(22)} ${byGroup.get(g) || 0}`);
