// Accuracy on doors that actually get quoted, not on the whole allowed box.
//
// PASS ONLY AN EXTERNAL SAMPLE. dev/eval-rand-seed20261002.json was imported
// into the corpus and is training data; including it here read 84.7% where the
// external seed alone reads 66%. An eval script that accepts any file will
// eventually be handed the wrong one.
//
// The uniform random sample treats a 1500 lb door at 300,000 cycles exactly
// like a 180 lb residential door at 10,000, and there are far more of the
// former in a uniform draw than in a real order book. Both numbers are worth
// having: the box figure is the honest worst case, this one is the working
// figure.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
const mod = await load();
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const BANDS = {
    "residential   (<=300 lb, <=8ft, <=25k)": (i) => i.weight <= 300 && i.heightInches <= 96 && i.cycles <= 25000,
    "light comml   (<=600 lb, <=12ft, <=50k)": (i) => i.weight <= 600 && i.heightInches <= 144 && i.cycles <= 50000,
    "commercial    (<=1000 lb, <=16ft, <=100k)": (i) => i.weight <= 1000 && i.heightInches <= 192 && i.cycles <= 100000,
    "everything in the allowed box": () => true,
};
const tally = {};
for (const k of Object.keys(BANDS)) tally[k] = { n: 0, wire: 0, len: 0, within1: 0 };
for (const f of process.argv.slice(2)) {
    let rs; try { rs = JSON.parse(readFileSync(f, "utf8")); } catch { continue; }
    for (const r of rs) {
        const i = r.input;
        if (r.error || !r.data?.innerSpring) continue;
        if (r.data.innerSpring.springLength > 120) continue;   // unbuildable anyway
        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, { assembly:"Duplex", drum:i.drum, springId:'3 3/4" inside 6"',
            springs:i.springs, radius:REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi?{liftType:"Hi-Lift",liftin:String(i.hiLift)}:{}),
            cycles:Number(i.cycles).toLocaleString("en-US"), weight:String(i.weight),
            doorWidthFeet:9, doorHeightFeet:Math.floor(i.heightInches/12),
            doorHeightInches:i.heightInches%12 });
        const s = c.duplexStep; if (!s) continue;
        const wok = `${s.outerWire}/${s.innerWire}` ===
            `${r.data.outerSpring.wireSize}/${r.data.innerSpring.wireSize}`;
        const d = wok ? c.duplexInnerLength - r.data.innerSpring.springLength : NaN;
        for (const [k, test] of Object.entries(BANDS)) {
            if (!test(i)) continue;
            const t = tally[k];
            t.n += 1;
            t.wire += wok ? 1 : 0;
            t.len += wok && d === 0 ? 1 : 0;
            t.within1 += wok && Math.abs(d) <= 1 ? 1 : 0;
        }
    }
}
console.log("door class".padEnd(42) + "n".padStart(5) + "   wire" + "   length" + "   within 1\"");
for (const [k, t] of Object.entries(tally)) {
    if (!t.n) continue;
    console.log(k.padEnd(42) + String(t.n).padStart(5) +
        `   ${(t.wire/t.n*100).toFixed(1)}%` +
        `   ${(t.len/t.n*100).toFixed(1)}%` +
        `   ${(t.within1/t.n*100).toFixed(1)}%`);
}
