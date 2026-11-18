// ACCURACY BY DOOR HEIGHT - THE ENVELOPE THE SHOP CAN ACTUALLY BE ASKED FOR.
//
//   node dev/by-door-height.mjs
//
// Owner, 2026-11-12: "our max height for doors is 220\" so it is a
// possibility that we will need to make springs for doors of that height".
//
// EVERY EARLIER CUT OF THIS BAND WAS BY SPRING LENGTH, which is a derived
// quantity and not something a customer orders. A spring 220" long and a door
// 220" tall are different things, and the question that matters commercially
// is the second: for the doors he can be asked to build, how right are we?
//
// If the catastrophic bucket turns out to be doors TALLER than 220", it is
// outside his envelope and the honest figure is much better than 56%.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const MAX = Number(process.env.MAX_HEIGHT) || 220;
const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const s = c.duplexStep;

    if (!s) continue;

    const rung = `${s.outerWire}/${s.innerWire}`;
    const wireOk = rung === `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`;
    const h = (Number(r.state.doorHeightFeet) || 0) * 12
        + (Number(r.state.doorHeightInches) || 0);

    rows.push({
        h,
        springLen: Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength),
        wireOk,
        ok: wireOk
            && c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

const show = (name, g) => {
    if (!g.length) return;

    console.log(`  ${name.padEnd(30)}${String(g.length).padStart(6)}  `
        + `${(g.filter((x) => x.ok).length / g.length * 100).toFixed(2).padStart(6)}%  `
        + `${(g.filter((x) => x.wireOk).length / g.length * 100).toFixed(2).padStart(7)}%`);
};

console.log(`${rows.length} duplex readings\n`);
console.log("1. BY DOOR HEIGHT - what a customer can order\n");
console.log("  band                               n    exact   wire right");

for (const [lo, hi] of [[0, 96], [96, 144], [144, 180], [180, 220], [220, 1e9]]) {
    show(`${lo}-${hi === 1e9 ? "+" : hi}" tall`,
        rows.filter((x) => x.h > lo && x.h <= hi));
}

console.log("");
show("DOORS HE CAN BUILD (<=220\")", rows.filter((x) => x.h <= MAX));
show("doors taller than 220\"", rows.filter((x) => x.h > MAX));

console.log("\n2. THE SAME SPRING-LENGTH BANDS, BUT ONLY FOR BUILDABLE DOORS\n");
console.log("  band                               n    exact   wire right");

const inEnv = rows.filter((x) => x.h <= MAX);

for (const [lo, hi] of [[0, 96], [96, 120], [120, 1e9]]) {
    show(`spring ${lo}-${hi === 1e9 ? "+" : hi}"`,
        inEnv.filter((x) => x.springLen > lo && x.springLen <= hi));
}

console.log("\n3. WHO IS IN THE PAST-120\" BAND, BY DOOR HEIGHT\n");
console.log("  band                               n    exact   wire right");

const past = rows.filter((x) => x.springLen > 120);

for (const [lo, hi] of [[0, 144], [144, 180], [180, 220], [220, 1e9]]) {
    show(`${lo}-${hi === 1e9 ? "+" : hi}" tall`,
        past.filter((x) => x.h > lo && x.h <= hi));
}

const tall = past.filter((x) => x.h > MAX).length;

console.log(`\n  ${tall} of ${past.length} past-120" readings are doors TALLER `
    + `than ${MAX}" - outside the envelope.`);
