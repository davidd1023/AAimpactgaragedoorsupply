// WHY DO SHORT HEAVY DOORS NEED LONG SPRINGS, AND WHERE EXACTLY DO WE MISS?
//
//   node dev/over120-mechanism.mjs
//
// Owner, 2026-11-12, after being told the past-120" band was absurd doors:
// "our max height for doors is 220\"". The re-cut by DOOR HEIGHT then showed
// the opposite of what had been assumed - the worst bucket is doors UNDER
// 144" tall at 49.4% exact, and only 62 of 608 readings are doors taller than
// 220". These are HEAVY doors, not tall ones, and every one of them is
// orderable.
//
// So this looks for the mechanism among the things that make a door heavy
// rather than tall: the weight against the drum's own rating (the engine
// CLAMPS to it, which my own notes call a corrupt reading when the reference
// is asked about the unclamped figure), the spring count carrying that
// weight, and the cycle target.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const limitsFor = (d) => mod.HILIFT_DRUMS[d] || mod.DRUM_LIMITS[d] || null;
const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const s = c.duplexStep;

    if (!s) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;

    if (rung !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) continue;

    const refMax = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);

    if (refMax <= 120) continue;

    const lim = limitsFor(r.state.drum);
    const w = Number(r.state.weight) || 0;

    rows.push({
        h: (Number(r.state.doorHeightFeet) || 0) * 12
            + (Number(r.state.doorHeightInches) || 0),
        w,
        // HOW CLOSE THE DOOR IS TO THE DRUM'S OWN RATING. 1.0 means the
        // engine clamped; above 1.0 means the request asked the reference
        // about a heavier door than we computed, which is the corrupt case.
        load: lim && lim.maxWeight ? w / lim.maxWeight : null,
        springs: c.duplexSpringCount,
        cycles: Number(String(r.state.cycles).replace(/,/g, "")) || 0,
        perSpring: w / (c.duplexSpringCount || 1),
        d: c.duplexInnerLength - r.expect.duplexInnerLength,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

const show = (name, g) => {
    if (!g.length) return;

    console.log(`  ${name.padEnd(26)}${String(g.length).padStart(5)}  `
        + `${(g.filter((x) => x.ok).length / g.length * 100).toFixed(1).padStart(6)}%`);
};

console.log(`${rows.length} past-120" readings with the wire right\n`);

console.log("1. BY WEIGHT AGAINST THE DRUM'S OWN RATING\n");
console.log("  band                          n    exact");

for (const [lo, hi] of [[0, 0.5], [0.5, 0.75], [0.75, 0.95], [0.95, 1.001], [1.001, 9]]) {
    show(`${(lo * 100).toFixed(0)}-${(hi * 100).toFixed(0)}% of rating`,
        rows.filter((x) => x.load !== null && x.load > lo && x.load <= hi));
}

const over = rows.filter((x) => x.load !== null && x.load > 1.001);

console.log(`\n  ${over.length} readings ask about a door HEAVIER than the drum`
    + ` allows - the clamp case.`);

console.log("\n2. BY SPRING COUNT\n");
console.log("  band                          n    exact");

for (const n of [1, 2, 3, 4]) show(`${n} spring(s)`, rows.filter((x) => x.springs === n));

console.log("\n3. BY WEIGHT CARRIED PER SPRING\n");
console.log("  band                          n    exact");

for (const [lo, hi] of [[0, 200], [200, 350], [350, 500], [500, 750], [750, 1e9]]) {
    show(`${lo}-${hi === 1e9 ? "+" : hi} lb/spring`,
        rows.filter((x) => x.perSpring > lo && x.perSpring <= hi));
}

console.log("\n4. BY CYCLE TARGET\n");
console.log("  band                          n    exact");

for (const cy of [10000, 15000, 25000, 50000, 100000]) {
    show(`${cy.toLocaleString("en-US")} cycles`, rows.filter((x) => x.cycles === cy));
}

const high = rows.filter((x) => x.cycles >= 100000);

console.log("\n5. THE WORST CELL, CROSSED\n");
console.log("  band                          n    exact");
show("1 spring, 100k+ cycles", high.filter((x) => x.springs === 1));
show("1 spring, under 100k", rows.filter((x) => x.springs === 1 && x.cycles < 100000));
show("2+ springs, 100k+ cycles", high.filter((x) => x.springs > 1));
show("2+ springs, under 100k",
    rows.filter((x) => x.springs > 1 && x.cycles < 100000));
