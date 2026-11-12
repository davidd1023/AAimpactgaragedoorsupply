// AIM A DRAW AT THIN (rung, spring count) GROUPS - THE UNIT THE FITTER FITS.
//
//   node dev/group-target-sample.mjs <out.json> <seed> <budget> [samples]
//
// WHY THIS EXISTS AND WHY THE RUNG ALLOCATOR COULD NOT DO IT. `lineByCount`
// holds a separate line per spring count, so a rung can hold 320 readings
// while the 2-spring group inside it holds 9. `dev/rung-target-sample.mjs`
// cannot see that: it fills rungs, so "the rung is at target" has never meant
// "the group that is failing has any data".
//
// THAT IS WHY BATCH S2 BOUGHT NOTHING. It filled `0.3938/0.3195` from 124 to
// 320 readings and not one of its six failures moved - because 124 was
// ALREADY past the point where more data helps. `dev/group-density.mjs`
// measures where that point is:
//
//     group size   readings   failures   rate
//     1-9              187         28    14.97%
//     10-24            332          9     2.71%
//     25-49           1159         19     1.64%
//     50-99           2160         42     1.94%
//     100-249         6249        121     1.94%
//     250+            1876         37     1.97%
//
// FLAT FROM 25 UPWARD, over 11,444 readings and four bands. So concentrating
// on the big failing groups is provably useless, and the ONLY place data can
// still pay is the 1-9 band - 22 groups carrying 28 failures at fifteen per
// cent against a 1.9% floor.
//
// THE TARGET IS 25, NOT 320, and that is the whole point: 25 is the elbow of
// that curve. Filling past it is what S2 did.
//
// REACHABILITY IS CHECKED FIRST, because a rare group is rare in the door
// space rather than merely unvisited - S2 found a rung needing 302 readings
// where 60,000 draws held 27. Of the 22 thin groups, 15 take >=20 draws in
// 60,000 and 7 effectively cannot be reached at all; one got zero. This
// sampler reports what it could not reach rather than silently drawing short.
//
// THESE ARE TRAINING READINGS, NOT A YARDSTICK, so no `eval` flag and the
// output must NOT be named eval-*.
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
const TARGET = Number(process.env.TARGET) || 25;
const THIN = Number(process.env.THIN) || 9;
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
    if (Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength) > 120) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;
    const g = `${rung}|${c.duplexSpringCount}`;
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
    if (h.n <= THIN && h.bad > 0) want.set(g, TARGET - h.n);
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
    if (!(c.duplexOuterLength > 0) || c.duplexOuterLength > 120) continue;

    const g = `${s.outerWire}/${s.innerWire}|${c.duplexSpringCount}`;
    const room = want.get(g);

    if (!room || (got.get(g) ?? 0) >= room) continue;

    drawn.add(key);
    got.set(g, (got.get(g) ?? 0) + 1);
    cases.push({
        label: `grp ${g} ${cases.length}`,
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
    const [rung, spr] = g.split("|");

    console.log(`  ${`${rung} ${spr}spr`.padEnd(26)}${String(h.n).padStart(4)}`
        + `${String(h.bad).padStart(7)}${String(d).padStart(8)}   `
        + `${room - d > 0 ? room - d : ""}`);
}

const missed = [...want].filter(([g]) => !got.has(g)).length;

console.log(`\n  ${missed} group(s) the sampler could not reach at all`
    + ` - rare in the door space, not merely unvisited.`);
