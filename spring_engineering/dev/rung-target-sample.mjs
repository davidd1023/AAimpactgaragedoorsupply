// Draw a sweep AIMED at the rungs that are short of length readings.
//
//   node dev/rung-target-sample.mjs <out.json> <seed> <budget> [samples]
//
// WHY AIM AT ALL. dev/rung-volume.sh shows per-rung length volume causes length
// accuracy: starving a rung to 160 readings costs it 7 points and the curve is
// still climbing at 320. Only 4 of 50 rungs are above 300. Uniform data cannot
// fix that - it lands in proportion to how often a door hits a rung, so it
// piles onto the four that are already at 100% and adds a median of 14 readings
// to a thin one.
//
// THE RUNG IS AN OUTPUT, so it cannot be requested. The reference picks the
// wire pair from the door. But our own pair is right 99.1% of the time, so the
// model is an adequate targeting system: sample geometries locally for nothing,
// keep the ones it says land on a wanted rung, and spend a request only on
// those.
//
// NOT BOUNDARY-DENSE, deliberately. A batch chosen by where a fitted threshold
// sits is the wrong data for the rung's stiffness and drags sMult - that is the
// documented mechanism behind the R1 and P1 batches. A rung is a broad region,
// not a boundary, so selecting on it does not concentrate near the snap.
//
// NO eval STAMP. These readings are meant to be FITTED - that is their whole
// purpose - so they must land on a dev/pulled-*.json name derive.mjs ingests.
// The never-tuned draws stay untouched and remain the yardstick.
import { load, make } from "./harness.mjs";
import { writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { stateFromReading, isClean, isModelledDuplex } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const [out, seedArg, budgetArg, samplesArg] = process.argv.slice(2);

if (!out || !seedArg || !budgetArg) {
    console.error("usage: node dev/rung-target-sample.mjs <out.json> <seed> <budget> [samples]");
    process.exit(1);
}

if (existsSync(out) && !process.env.OVERWRITE) {
    console.error(`${out} already exists - refusing to overwrite it.`);
    process.exit(1);
}

const BUDGET = Number(budgetArg);
const SAMPLES = Number(samplesArg) || 30000;
const TARGET = Number(process.env.TARGET) || 320;
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

// --- where we stand, and which rungs a real door actually visits -------------
const cal = mod.DUPLEX_PAIRS['3 3/4" inside 6"'].calibration;
const have = new Map(cal.map((c) => [`${c.outerWire}/${c.innerWire}`, c.n]));
const traffic = new Map();

for (const f of readdirSync(HERE).filter((x) => /^eval-validation.*\.json$/.test(x))) {
    for (const r of JSON.parse(readFileSync(join(HERE, f), "utf8"))) {
        const i = r.input, d = r.data;

        if (!d || r.error || !isModelledDuplex(i) || !isClean(r)) continue;
        if (!d.innerSpring?.springLength || !d.outerSpring?.wireSize) continue;

        const rung = `${parseFloat(d.outerSpring.wireSize)}/${parseFloat(d.innerSpring.wireSize)}`;

        traffic.set(rung, (traffic.get(rung) || 0) + 1);
    }
}

// A geometry we already hold teaches nothing, so it must not be bought twice.
const held = new Set();
const geomKey = (st) => [st.drum, st.springs, st.radius, st.liftType ?? "Standard",
    st.liftin ?? "", st.cycles, st.weight, st.doorHeightFeet,
    st.doorHeightInches ?? 0].join("|");

for (const r of JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8")).readings) {
    if (r.state) held.add(geomKey(r.state));
}

for (const f of readdirSync(HERE).filter((x) => /^pulled.*\.json$/.test(x))) {
    let data;

    try { data = JSON.parse(readFileSync(join(HERE, f), "utf8")); } catch { continue; }

    for (const r of data) {
        if (r.input && isModelledDuplex(r.input)) held.add(geomKey(stateFromReading(r.input)));
    }
}

console.log(`already hold ${held.size} distinct geometries`);

// --- sample geometries and bucket them by the rung we predict ----------------
const STD = Object.keys(mod.DRUMS), HI = Object.keys(mod.HILIFT_DRUMS);
const LIM = mod.DRUM_LIMITS;
const CYCLES = ["10,000", "15,000", "25,000", "50,000", "75,000", "100,000",
    "150,000", "200,000", "250,000", "300,000"];
const RADII = ["LHR", "12", "15"];

let seed = Number(seedArg) || 1;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const between = (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1));
const buckets = new Map();

for (let k = 0; k < SAMPLES; k++) {
    const hi = rnd() < 0.35;
    const drum = pick(hi ? HI : STD);
    const lim = LIM[drum] || { maxHeight: 144, maxWeight: 750 };
    const heightIn = between(84, Math.min(lim.maxHeight ?? 144, 240));
    const st = {
        assembly: "Duplex", springId: '3 3/4" inside 6"', drum,
        springs: between(1, 4), radius: hi ? "15" : pick(RADII),
        liftType: hi ? "Hi-Lift" : "Standard",
        liftin: hi ? String(between(12, Math.min(120, lim.maxHiLift ?? 120))) : "",
        cycles: pick(CYCLES), weight: String(between(150, lim.maxWeight ?? 750)),
        doorWidthFeet: 18, doorWidthInches: 0,
        doorHeightFeet: Math.floor(heightIn / 12), doorHeightInches: heightIn % 12,
    };

    if (held.has(geomKey(st))) continue;

    let c, s;

    try { c = make(mod, st); s = c.duplexStep; } catch { continue; }

    if (!s) continue;

    // Our own warnings as the buildability filter. A reading the reference
    // flags keeps its wire and loses its length, so a flagged one buys nothing
    // for the quantity this campaign is after.
    if ((c.warnings || []).some((w) => w && w.severity !== "info")) continue;

    const L = c.duplexInnerLength;

    if (!(L > 0) || L > 120) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;

    if (!buckets.has(rung)) buckets.set(rung, []);

    buckets.get(rung).push(st);
}

// --- allocate the budget: most points per request first ----------------------
const need = [...traffic].map(([rung, n]) => ({
    rung, traffic: n,
    have: have.get(rung) ?? 0,
    need: Math.max(0, TARGET - (have.get(rung) ?? 0)),
    pool: (buckets.get(rung) || []).length,
})).filter((r) => r.need > 0 && r.pool > 0)
    .sort((a, b) => (b.traffic / b.need) - (a.traffic / a.need));

const cases = [];

for (const r of need) {
    if (cases.length >= BUDGET) break;

    const take = Math.min(r.need, r.pool, BUDGET - cases.length);
    const pool = buckets.get(r.rung);

    for (let k = 0; k < take; k++) {
        const st = pool[k];

        cases.push({
            label: `vol ${r.rung} ${k}`, garageDoorLineId: lineId,
            assembly: "Duplex", lift: st.liftType === "Hi-Lift" ? "HiLift" : "Standard",
            radius: st.radius === "LHR" ? 10 : Number(st.radius),
            springs: st.springs, innerId: 3.75, outerId: 6, drum: st.drum,
            cycles: Number(st.cycles.replace(/,/g, "")),
            widthInches: 216,
            heightInches: st.doorHeightFeet * 12 + st.doorHeightInches,
            weight: Number(st.weight),
            ...(st.liftType === "Hi-Lift" ? { hiLift: Number(st.liftin) } : {}),
        });
    }

    r.took = take;
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`\nwrote ${cases.length} targeted cases to ${out} (seed ${seedArg}, target ${TARGET})\n`);
console.log("rung            have   need  traffic   pool   taken");

for (const r of need) {
    if (!r.took) continue;

    console.log(`${r.rung.padEnd(14)}${String(r.have).padStart(6)}${String(r.need).padStart(7)}`
        + `${String(r.traffic).padStart(9)}${String(r.pool).padStart(7)}${String(r.took).padStart(8)}`);
}
