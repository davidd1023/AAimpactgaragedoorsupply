// AIM A DRAW AT THE PAST-120" RUNGS, TO SHARPEN THEIR OFFSETS.
//
//   node dev/over120-target-sample.mjs <out.json> <seed> <budget> [samples]
//
// WHY THIS BAND HAS NEVER BEEN FED DIRECTLY. Batch V16 reached it by accident
// (heavy rungs in SOFT mode) and `dev/group-target-sample.mjs` deliberately
// EXCLUDED it - its filter was `duplexOuterLength <= 120`, because it was
// chasing in-envelope groups. So the past-120" offsets are fitted on about
// EIGHT readings a rung, which `dev/group-density.mjs` measured as squarely
// inside the regime where data still pays eight times over.
//
// AND FLAGGED READINGS FEED THIS TABLE, unlike the bonus table. `derive.mjs`
// drops a flagged reading's LENGTH from the rung fit; `derive-over120.mjs`
// does not, because it is fitting the length error directly against whatever
// the reference returned. These doors are nearly all flagged - the reference
// says "only spring lengths between 0 and 120 are supported" - so a 7% clean
// rate is irrelevant here in a way it was not for G1.
//
// WHAT IT CANNOT BUY, measured 2026-11-12 before this was written: a better
// FORM. Five were tried and all lost - a global second term, a per-(rung,
// count) key, a frac band per rung, one global frac rule, and a per-rung
// line. The per-rung constant at 57.5% out of sample is this form's ceiling,
// so what is left to buy is a SHARPER constant, not a different rule.
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { makeRnd } from "./rnd.mjs";
import { stateFromReading, isModelledDuplex } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, budgetArg, samplesArg] = process.argv.slice(2);

if (!out || !seedArg || !budgetArg) {
    console.error("usage: node dev/group-target-sample.mjs <out.json> <seed> <budget> [samples]");
    process.exit(1);
}

if (existsSync(out) && !process.env.OVERWRITE) {
    console.error(`${out} already exists - refusing to overwrite it.`);
    process.exit(1);
}

const BUDGET = Number(budgetArg);
const SAMPLES = Number(samplesArg) || 90000;
const TARGET = Number(process.env.TARGET) || 22;
const THIN = Number(process.env.THIN) || 40;
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));

let lineId = null;

for (const f of readdirSync(HERE).filter((x) => /^sweeps.*\.json$/.test(x))) {
    const hit = JSON.parse(readFileSync(join(HERE, f), "utf8")).find((c) => c.garageDoorLineId);

    if (hit) { lineId = hit.garageDoorLineId; break; }
}

if (!lineId) {
    console.error("no garageDoorLineId found in dev/sweeps*.json");
    process.exit(1);
}

// What the corpus holds per group, in-envelope only, and which of those
// groups are both THIN and FAILING - the only ones worth a request.
const held = new Set();
const geomKey = (st) => [st.drum, st.springs, st.radius, st.liftType ?? "Standard",
    st.liftin ?? "", st.cycles, st.weight, st.doorHeightFeet,
    st.doorHeightInches ?? 0].join("|");
const group = new Map();

for (const r of corpus.readings) {
    if (r.state) held.add(geomKey(r.state));
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const s = c.duplexStep;

    if (!s) continue;
    if (Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength) <= 120) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;
    const g = rung;
    const ok = rung === `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`
        && c.duplexInnerLength === r.expect.duplexInnerLength
        && c.duplexOuterLength === r.expect.duplexOuterLength;

    if (!group.has(g)) group.set(g, { n: 0, bad: 0 });

    const h = group.get(g);

    h.n++;
    if (!ok) h.bad++;
}

// Anything already pulled counts as held, so no request is paid twice.
for (const f of readdirSync(HERE).filter((x) => /^pulled.*\.json$/.test(x))) {
    let data;

    try { data = JSON.parse(readFileSync(join(HERE, f), "utf8")); } catch { continue; }

    for (const r of data) {
        if (r.input && isModelledDuplex(r.input)) held.add(geomKey(stateFromReading(r.input)));
    }
}

const want = new Map();

for (const [g, h] of group) {
    if (h.n <= THIN) want.set(g, TARGET - h.n);
}

console.log(`${want.size} thin (<=${THIN}) failing groups, target ${TARGET} readings each`);
console.log(`room for ${[...want.values()].reduce((a, b) => a + b, 0)} readings, `
    + `budget ${BUDGET}\n`);

const STD = Object.keys(mod.DRUMS), HI = Object.keys(mod.HILIFT_DRUMS);
const limitsFor = (d) => mod.HILIFT_DRUMS[d] || mod.DRUM_LIMITS[d] || null;
const CYCLES = ["10,000", "25,000", "50,000", "100,000"];
const RADII = ["15", "12", "LHR"];
const { rnd, pick, between } = makeRnd(seedArg);
const drawn = new Set();
const cases = [];
const got = new Map();

for (let k = 0; k < SAMPLES && cases.length < BUDGET; k++) {
    const hi = rnd() < 0.5;          // thin groups skew heavy, so hi-lift more often
    const drum = pick(hi ? HI : STD);
    const lim = limitsFor(drum) || { maxHeight: 144, maxWeight: 750 };
    const heightIn = between(84, Math.min(lim.maxHeight ?? 144, 240));
    const st = {
        assembly: "Duplex", springId: '3 3/4" inside 6"', drum,
        springs: between(1, 4), radius: hi ? "15" : pick(RADII),
        liftType: hi ? "Hi-Lift" : "Standard",
        liftin: hi ? String(between(12, Math.min(120, lim.maxHiLift ?? 120))) : "",
        cycles: pick(CYCLES),
        weight: String(between(150, lim.maxWeight ?? 750)),
        doorWidthFeet: 18, doorWidthInches: 0,
        doorHeightFeet: Math.floor(heightIn / 12), doorHeightInches: heightIn % 12,
    };
    const key = geomKey(st);

    if (held.has(key) || drawn.has(key)) continue;

    let c, s;

    try { c = make(mod, st); s = c.duplexStep; } catch { continue; }

    if (!s) continue;

    // IN-ENVELOPE ONLY. A reading past 120" teaches this band nothing and the
    // reference disclaims it anyway.
    if (!(c.duplexInnerLength > 119)) continue;   // PAST the line, not inside it

    const g = `${s.outerWire}/${s.innerWire}`;
    const room = want.get(g);

    if (!room || (got.get(g) ?? 0) >= room) continue;

    drawn.add(key);
    got.set(g, (got.get(g) ?? 0) + 1);
    cases.push({
        label: `o120 ${g} ${cases.length}`,
        garageDoorLineId: lineId,
        assembly: "Duplex", innerId: 3.75, outerId: 6,
        drum, springs: st.springs,
        radius: st.radius === "LHR" ? 10 : Number(st.radius),
        lift: hi ? "HiLift" : "Standard",
        ...(hi ? { hiLift: Number(st.liftin) } : {}),
        cycles: Number(String(st.cycles).replace(/,/g, "")),
        weight: Number(st.weight),
        widthInches: 216,
        heightInches: heightIn,
    });
}

// THE LAST GATE BEFORE THE ACCOUNT IS SPENT - the V13 guard, asserting the
// sweep rather than the generator so it catches a repeat whatever caused it.
const distinct = new Set(cases.map((c) => [c.drum, c.springs, c.radius, c.lift,
    c.hiLift ?? "", c.cycles, c.weight, c.heightInches].join("|")));

if (distinct.size !== cases.length) {
    console.error(`REFUSING TO WRITE: ${cases.length} cases, ${distinct.size} distinct.`);
    process.exit(1);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`wrote ${cases.length} cases to ${out} (seed ${seedArg}, `
    + `${SAMPLES} geometries sampled)\n`);
console.log("  group                      held  fails   drawn   short by");

for (const [g, room] of [...want].sort((a, b) => (got.get(b[0]) ?? 0) - (got.get(a[0]) ?? 0))) {
    const h = group.get(g);
    const d = got.get(g) ?? 0;
    const rung = g; const spr = "";

    console.log(`  ${`${rung} ${spr}spr`.padEnd(26)}${String(h.n).padStart(4)}`
        + `${String(h.bad).padStart(7)}${String(d).padStart(8)}   `
        + `${room - d > 0 ? room - d : ""}`);
}

const missed = [...want].filter(([g]) => !got.has(g)).length;

console.log(`\n  ${missed} group(s) the sampler could not reach at all`
    + ` - rare in the door space, not merely unvisited.`);
