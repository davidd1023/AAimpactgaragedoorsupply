// The length error distribution on external samples: how many readings are
// exact, how many are off by an inch, how many are worse.
//
//   node dev/length-errors.mjs dev/eval-rand-seed777001.json [...]
//
// Pass only EXTERNAL files. Readings needing a spring over 120" are excluded
// because the reference refuses to build them, and wire misses are counted
// separately so the length figure is about length.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const err = new Map();
let n = 0, wireBad = 0, over120 = 0;

for (const file of process.argv.slice(2)) {
    let rows;

    try {
        rows = JSON.parse(readFileSync(file, "utf8"));
    } catch {
        continue;
    }

    for (const r of rows) {
        const i = r.input;

        if (r.error || !r.data || !r.data.innerSpring) continue;
        if ((i.assembly ?? "Duplex") !== "Duplex" || Number(i.innerId) !== 3.75) continue;

        const refL = r.data.innerSpring.springLength;
        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, {
            assembly: "Duplex", drum: i.drum, springId: '3 3/4" inside 6"',
            springs: i.springs,
            radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
            doorWidthInches: (i.widthInches ?? 108) % 12,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const s = c.duplexStep;

        if (!s) continue;

        n += 1;

        if (refL > 120) { over120 += 1; continue; }

        if (`${s.outerWire}/${s.innerWire}` !==
            `${r.data.outerSpring.wireSize}/${r.data.innerSpring.wireSize}`) {
            wireBad += 1;
            continue;
        }

        const d = Math.round((c.duplexInnerLength - refL) * 100) / 100;

        err.set(d, (err.get(d) ?? 0) + 1);
    }
}

const scored = [...err.values()].reduce((a, b) => a + b, 0);
let exact = 0, inch = 0, worse = 0;

for (const [d, k] of err) {
    if (d === 0) exact += k;
    else if (Math.abs(d) <= 1.25) inch += k;
    else worse += k;
}

console.log(`${n} readings  (${over120} need a spring over 120", ${wireBad} wire miss)`);
console.log(`of the ${scored} buildable with the wire agreeing:`);

for (const [d, k] of [...err].sort((a, b) => a[0] - b[0])) {
    console.log(`   ${d > 0 ? "+" : ""}${d.toFixed(2).padStart(6)}"   ${String(k).padStart(4)}   ${(k / scored * 100).toFixed(1)}%`);
}

console.log(`\n  exact          ${exact}/${scored} = ${(exact / scored * 100).toFixed(1)}%`);
console.log(`  within 1 inch  ${exact + inch}/${scored} = ${((exact + inch) / scored * 100).toFixed(1)}%`);
console.log(`  worse          ${worse}/${scored} = ${(worse / scored * 100).toFixed(1)}%`);
