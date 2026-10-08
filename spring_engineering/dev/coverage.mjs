// How much of the ALLOWED parameter space has actually been tested.
//
// dev/by-drum.mjs reports the span of each input, which overstates coverage:
// "weights 216-1500 (789)" says nothing about whether the 789 are spread
// across spring counts, radii and targets or piled into one corner. This walks
// the allowed box per drum - weight up to maxWeight, height up to maxHeight,
// every spring count, every radius the drum offers, every cycle target - and
// counts cells with no reading in them.
//
// A cell is covered if some reading shares its spring count, radius, target,
// height band and weight band. The weight band is 25 lb, because that is about
// the spacing at which the wire choice changes.
import { load } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
const c = JSON.parse(readFileSync("./dev/corpus.json", "utf8"));
const TARGETS = ["10,000", "15,000", "25,000", "50,000", "100,000", "200,000", "300,000"];
const WBAND = 25;
const HBAND = 24;

const seen = new Set();
for (const r of c.readings) {
    if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) continue;
    const st = r.state;
    const h = Number(st.doorHeightFeet) * 12 + Number(st.doorHeightInches || 0);
    seen.add([st.drum, st.springs, st.radius, st.cycles,
        Math.floor(h / HBAND), Math.floor(Number(st.weight) / WBAND)].join("|"));
}

const DRUMS = {
    "CANIMEX/TF D400-96":  { w: [220, 530],  h: [84, 96],   radii: ["12", "15", "LHR"] },
    "CANIMEX/TF D400-144": { w: [220, 750],  h: [84, 144],  radii: ["12", "15", "LHR"] },
    "CANIMEX/TF D525-216": { w: [220, 1500], h: [84, 216],  radii: ["12", "15", "LHR"] },
    "CANIMEX/TF D800-120": { w: [300, 2000], h: [84, 192],  radii: ["15"] },
    "CANIMEX/TF 575-120":  { w: [250, 1000], h: [84, 192],  radii: ["15"] },
    "CANIMEX/TF 525-54HL": { w: [250, 1000], h: [84, 192],  radii: ["15"] },
};

console.log("drum".padEnd(14) + "cells".padStart(8) + "covered".padStart(9) + "  %" + "   biggest hole");
let total = 0, hit = 0;
for (const [drum, box] of Object.entries(DRUMS)) {
    let n = 0, got = 0;
    const missBy = new Map();
    for (let sp = 1; sp <= 4; sp++) {
        for (const rad of box.radii) {
            for (const t of TARGETS) {
                for (let h = box.h[0]; h <= box.h[1]; h += HBAND) {
                    for (let w = box.w[0]; w <= box.w[1]; w += WBAND) {
                        n += 1;
                        const key = [drum, sp, rad, t, Math.floor(h / HBAND),
                            Math.floor(w / WBAND)].join("|");
                        if (seen.has(key)) got += 1;
                        else missBy.set(`${sp}spr t${t}`, (missBy.get(`${sp}spr t${t}`) ?? 0) + 1);
                    }
                }
            }
        }
    }
    total += n; hit += got;
    const worst = [...missBy].sort((a, b) => b[1] - a[1])[0];
    console.log(drum.split(" ").pop().padEnd(14) + String(n).padStart(8) +
        String(got).padStart(9) + `  ${(got / n * 100).toFixed(1)}%` +
        `   ${worst ? `${worst[0]} (${worst[1]} cells)` : "-"}`);
}
console.log(`\n  overall ${hit}/${total} = ${(hit / total * 100).toFixed(1)}% of the allowed box has a reading`);
console.log(`  (cells are ${WBAND} lb x ${HBAND} in x spring count x radius x target)`);
