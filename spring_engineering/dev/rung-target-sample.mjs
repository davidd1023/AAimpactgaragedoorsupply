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
import { makeRnd } from "./rnd.mjs";

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

// RUNGS=0.3625/0.295[,...] SPENDS THE WHOLE BUDGET ON NAMED RUNGS, AND THE
// REASON IS THE OWNER'S OWN DOOR.
//
// The default allocation ranks by traffic/need - how often a real door lands
// on a rung over how short it is - which is the right rule for the catalogue
// as a whole and CANNOT EVER REACH A RARE RUNG. His 1067 lb door sits on
// 0.3625/0.295, which carries traffic 4 of 31 in the validation sets: needing
// 200 readings it scores 0.02, sorts dead last, and waits for every common
// rung to fill first. Batch V14 fed seven rungs and gave his none.
//
// A rung nobody visits is still somebody's door. This is the override for
// "fix the door in front of me" as against "raise the average", and the two
// are different jobs.
const ONLY = (process.env.RUNGS || "").split(",").map((s) => s.trim()).filter(Boolean);

// SOFT=1 keeps doors that carry a non-purchasable warning. See the filter
// below for what it does and does not let through, and whose instruction it is.
const SOFT = !!process.env.SOFT;
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

const { rnd, pick, between } = makeRnd(seedArg);
const buckets = new Map();

// A GEOMETRY THIS DRAW HAS ALREADY TAKEN, which is separate from `held` and is
// the lesson of batch V13: `held` answers "do we own this reading", and nothing
// answered "have I already put this one in the basket". The generator was
// collapsing onto a few hundred geometries (see dev/rnd.mjs) and every repeat
// passed the `held` check honestly, so 400 requests bought 21 distinct doors
// and the importer reported the other 379 as though the corpus had grown.
//
// The generator is fixed. This stands anyway: a sampler that can emit the same
// case twice is a sampler that can spend the owner's account on nothing, and
// the cost of being sure is a Set.
const drawn = new Set();

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
        cycles: pick(CYCLES),
        // IN SOFT MODE THE CEILING IS NOT A NUMBER ANYBODY TYPED. The three
        // standard drums carry a real rating in DRUM_LIMITS; the hi-lift drums
        // carry none, so the old `?? 750` fallback was a guess that happened
        // to sit below every heavy rung - which is half of why they starved.
        // Soft mode samples up to a generous ceiling and lets the engine's own
        // "heavier than this drum will allow" warning throw the rest out, so
        // the limit is the drum's rating as the engine knows it.
        weight: String(between(150, lim.maxWeight ?? (SOFT ? 3000 : 750))),
        doorWidthFeet: 18, doorWidthInches: 0,
        doorHeightFeet: Math.floor(heightIn / 12), doorHeightInches: heightIn % 12,
    };

    const key = geomKey(st);

    if (held.has(key) || drawn.has(key)) continue;

    drawn.add(key);

    let c, s;

    try { c = make(mod, st); s = c.duplexStep; } catch { continue; }

    if (!s) continue;

    // Our own warnings as the buildability filter. A reading the reference
    // flags keeps its wire and loses its length, so a flagged one buys nothing
    // for the quantity this campaign is after.
    //
    // SOFT=1 IS THE OWNER'S OWN INSTRUCTION, 2026-11-09: *"we need to improve
    // the accuracy of duplex springs EVEN IF THEY GIVE WARNINGS THAT WOULDNT
    // MAKE THEM PURCHASABLE"* - and that filter is what stood in the way.
    //
    // THE HEAVY HALF OF THE TABLE CANNOT BE REACHED WITHOUT IT. Measured:
    // every `0.625/*` group fails 100% of its length readings, 209 of the
    // failing readings sit on wire >= 0.4687, and those rungs hold 2 to 27
    // readings each. The reason is structural - a door heavy enough to need
    // 0.4615" wire ALWAYS trips "wire size exceeds 0.4375 maximum for the
    // outer spring inside diameter, Service Spring will not make it", so the
    // sampler discarded every one of them. It is a note about what the shop
    // can sell, not about whether the figures are right, and the owner asked
    // for the figures.
    //
    // WHAT STAYS EXCLUDED, AND WHY EACH:
    //
    //   - RED. Here that is "assembly will be too long for the door", which
    //     is a different door rather than a different spring.
    //   - THE DRUM-WEIGHT WARNING, which is not about buildability at all:
    //     the engine CLAMPS the weight to the drum's rating (it is a passing
    //     invariant that the weight used never exceeds it), so the request
    //     would ask the reference about a heavier door than we computed and
    //     the two answers would not be comparable. That is a corrupt
    //     reading, not an unsellable one.
    //
    // Soft readings are worth roughly 57% for LENGTH - that is the measured
    // share of heavy corpus readings the reference answers cleanly - against
    // 90% for ordinary doors. A flagged one still teaches the wire pairing.
    // 57% of something beats 100% of nothing, which is what these rungs get
    // today.
    const warned = (c.warnings || []).filter((w) => w && w.severity !== "info");
    const clamped = warned.some((w) =>
        /heavier than this drum will allow/i.test(w.text || w.message || ""));

    if (clamped) continue;

    if (SOFT ? warned.some((w) => w.severity === "red") : warned.length) continue;

    const L = c.duplexInnerLength;

    if (!(L > 0) || L > 120) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;

    if (!buckets.has(rung)) buckets.set(rung, []);

    buckets.get(rung).push(st);
}

// --- allocate the budget: most points per request first ----------------------
// With RUNGS set the candidates are the NAMED rungs, not the ones the
// validation sets happen to visit - a rare rung may have no traffic at all and
// would otherwise never even be a candidate. Ordered by how starved it is,
// since traffic is deliberately not the question any more.
const candidates = ONLY.length
    ? ONLY.map((rung) => [rung, traffic.get(rung) ?? 0])
    : [...traffic];

const need = candidates.map(([rung, n]) => ({
    rung, traffic: n,
    have: have.get(rung) ?? 0,
    need: Math.max(0, TARGET - (have.get(rung) ?? 0)),
    pool: (buckets.get(rung) || []).length,
})).filter((r) => r.need > 0 && r.pool > 0)
    .sort((a, b) => (ONLY.length
        ? b.need - a.need
        : (b.traffic / b.need) - (a.traffic / a.need)));

if (ONLY.length && !need.length) {
    console.error(`nothing to draw for ${ONLY.join(", ")}: either already at`
        + ` the target of ${TARGET}, or the sampler produced no geometry`
        + ` landing on it in ${SAMPLES} samples. Rung counts it does hold:`);
    for (const r of ONLY) {
        console.error(`  ${r}: have ${have.get(r) ?? 0},`
            + ` pool ${(buckets.get(r) || []).length}`);
    }
    process.exit(1);
}

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

// THE LAST GATE BEFORE THE OWNER'S ACCOUNT IS SPENT.
//
// Every request in this file costs a second of somebody else's server and a
// slice of his login. Batch V13 wrote 400 cases holding 21 distinct doors and
// nothing objected until the importer had already paid for them - so the file
// is now checked against what it claims to be, here, where it is still free.
//
// It asserts the sweep, not the generator: it would have caught V13 whatever
// the cause was, and it will catch the next cause too.
const distinct = new Set(cases.map((c) => [c.drum, c.springs, c.radius,
    c.lift, c.hiLift ?? "", c.cycles, c.weight, c.heightInches].join("|")));

if (distinct.size !== cases.length) {
    console.error(`REFUSING TO WRITE ${out}: ${cases.length} cases but only `
        + `${distinct.size} distinct geometries - ${cases.length - distinct.size}`
        + ` of these requests would ask the reference a question already asked`
        + ` in this same file. See dev/rnd.mjs; this is what spoiled batch V13.`);
    process.exit(1);
}

writeFileSync(out, JSON.stringify(cases, null, 1));
console.log(`\nwrote ${cases.length} targeted cases to ${out} (seed ${seedArg}, target ${TARGET})`);
console.log(`${distinct.size} distinct geometries, ${drawn.size} sampled\n`);
console.log("rung            have   need  traffic   pool   taken");

for (const r of need) {
    if (!r.took) continue;

    console.log(`${r.rung.padEnd(14)}${String(r.have).padStart(6)}${String(r.need).padStart(7)}`
        + `${String(r.traffic).padStart(9)}${String(r.pool).padStart(7)}${String(r.took).padStart(8)}`);
}
