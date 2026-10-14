// How our WIRE CHOICE compares with the reference's, split by lift.
// The warnings the owner met are downstream of this: a thicker wire than the
// reference picks is a wire over the limit for that ID and a longer spring
// than the door is wide.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
const mod = await load();
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const ID_TEXT = {1.75:'1 3/4"',2.625:'2 5/8"',3.75:'3 3/4"',4.375:'4 3/8"',5.25:'5 1/4"',6:'6"'};
const bucket = {};

for (const file of process.argv.slice(2)) {
    let rows; try { rows = JSON.parse(readFileSync(file, "utf8")); } catch { continue; }
    for (const r of rows) {
        const i = r.input ?? {};
        if (r.error || !r.data || (i.assembly ?? "Duplex") !== "Single") continue;
        const sp = r.data.innerSpring ?? r.data.outerSpring;
        if (!sp || !sp.wireSize || !ID_TEXT[sp.innerDiameter]) continue;
        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, {
            assembly: "Single", drum: i.drum, springId: ID_TEXT[sp.innerDiameter],
            springs: i.springs ?? 2, radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"), weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const ours = c.recommendedWire;
        if (ours === null || ours === undefined) continue;
        const key = hi ? "hi-lift" : "standard";
        const b = bucket[key] ??= { n: 0, same: 0, thicker: 0, thinner: 0, worst: 0 };
        b.n += 1;
        if (Math.abs(ours - sp.wireSize) < 1e-9) b.same += 1;
        else if (ours > sp.wireSize) { b.thicker += 1; b.worst = Math.max(b.worst, ours - sp.wireSize); }
        else b.thinner += 1;
    }
}
for (const [k, b] of Object.entries(bucket)) {
    const pc = (x) => ((100 * x) / b.n).toFixed(1).padStart(5) + "%";
    console.log(`${k.padEnd(9)} n=${String(b.n).padStart(4)}  same ${pc(b.same)}  we pick thicker ${pc(b.thicker)}  thinner ${pc(b.thinner)}  (largest overshoot ${b.worst.toFixed(4)}")`);
}
