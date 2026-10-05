// Score the SINGLE path's multiplier against reference Single readings.
//
// The multiplier is wire-independent, so it can be compared directly even
// though Single takes its wire from a dropdown while the reference picks one.
// It is also the whole chain: get it right and TIPPT, turns and length follow.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
const mod = await load();
let n = 0, ok = 0;
const bad = [];
for (const file of process.argv.slice(2)) {
    for (const r of JSON.parse(readFileSync(file, "utf8"))) {
        const i = r.input;
        if (r.error || i.assembly !== "Single" || !r.data) continue;
        const c = make(mod, {
            assembly: "Single", drum: i.drum, springId: '2 5/8"', springs: i.springs ?? 2,
            radius: { 10: "LHR", 12: "12", 15: "15" }[Number(i.radius)] ?? String(i.radius),
            cycles: Number(i.cycles).toLocaleString("en-US"), weight: String(i.weight),
            doorWidthFeet: 9, doorWidthInches: 0,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const d = Math.abs(c.multiplierExact - r.data.multiplier);
        n += 1;
        if (d < 2e-5) ok += 1;
        else bad.push(`   ${(i.label ?? "").padEnd(22)} ref ${r.data.multiplier}  ours ${c.multiplierExact.toFixed(6)}  (d=${d.toExponential(1)})`);
    }
}
console.log(`Single multiplier: ${ok}/${n} within 2e-5`);
if (bad.length) console.log(bad.join("\n"));
