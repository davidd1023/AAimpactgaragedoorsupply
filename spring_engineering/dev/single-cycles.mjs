// HOW ACCURATE IS THE SINGLE CYCLE-LIFE MODEL, AGAINST THE REFERENCE'S OWN?
//
//   node dev/single-cycles.mjs <eval files ...>
//
// WHY THIS EXISTS. Single is 2 wrong in 1,246 clean readings, and one of the
// two is a WIRE miss at exactly the D400-144's 750 lb rating. Probing the
// reference around that point showed it stepping up a wire between 735 and
// 750 lb, and its OWN reported cycle counts say why:
//
//     735 lb  0.295   -> 11,000 cycles        (target was 10,000)
//     750 lb  0.3065  -> 16,000 cycles
//
// At 735 the reference has barely 10% of margin left on 0.295, so 2% more
// load takes it under the target and it steps up. OUR model gives 0.295 at
// 750 lb **16,459 cycles** - no margin problem at all, so we stay. The wire
// rule is not wrong; the quantity it decides on is.
//
// THE COMPARISON IS NON-CIRCULAR ONLY WHERE THE WIRE AGREES. Where we picked
// a different wire, our figure describes our spring and theirs describes
// theirs, and comparing them compares two different springs - the duplex
// wire work nearly reported that artefact as a cause. So those are excluded.
//
// READ `cyclesForWire`, NOT `cycleLife`. The getter returns a FORMATTED
// STRING ("16,459"), which is the third invented-shape mistake this project
// has made; a diagnostic reading it numerically silently reports nothing.
//
// THE REFERENCE ROUNDS ITS OWN ANSWER to the nearest thousand, so a ratio
// inside a few per cent is as close as this measurement can see. Anything
// much larger is real.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { REF_RADIUS } from "./ref-state.mjs";

const mod = await load();
const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};
const SOLD = new Set([2.625, 3.75, 5.25]);
const files = process.argv.slice(2);

if (!files.length) {
    console.error("usage: node dev/single-cycles.mjs <eval files ...>");
    process.exit(1);
}

const rows = [];

for (const file of files) {
    let data;

    try { data = JSON.parse(readFileSync(file, "utf8")); } catch { continue; }

    for (const r of data) {
        const i = r.input, d = r.data;
        const sp = d?.outerSpring || d?.innerSpring;

        if (r.error || !sp?.wireSize || !i?.innerDiameter) continue;
        if (i.assembly !== "Single" || !(d?.cycles > 0)) continue;

        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(String(m)));

        if (msgs.length || r.status !== "success") continue;

        const idText = ID_TEXT[Number(i.innerDiameter)];

        if (!idText) continue;

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, {
            assembly: "Single", drum: i.drum, springId: idText,
            springs: i.springs ?? 2,
            radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
            doorWidthInches: (i.widthInches ?? 108) % 12,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });

        // ONLY where the wire agrees - otherwise the two figures describe
        // two different springs.
        if (c.recommendedWire === null
            || Math.abs(c.recommendedWire - sp.wireSize) > 1e-9) {
            continue;
        }

        const ours = c.cyclesForWire(sp.wireSize);

        if (!(ours > 0)) continue;

        rows.push({
            ratio: ours / Number(d.cycles), ours, theirs: Number(d.cycles),
            target: Number(i.cycles), id: Number(i.innerDiameter),
            sold: SOLD.has(Number(i.innerDiameter)),
            // how much margin the REFERENCE had over the target. The wire
            // rule takes the softest candidate that reaches it, so a
            // reading with little margin is one our error can flip.
            margin: Number(d.cycles) / Number(i.cycles),
        });
    }
}

const med = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
};
const show = (name, g) => {
    if (!g.length) return;

    const rs = g.map((x) => x.ratio);
    const s = rs.slice().sort((a, b) => a - b);

    console.log(`  ${name.padEnd(22)}${String(g.length).padStart(5)}  `
        + `${med(rs).toFixed(3).padStart(7)}  `
        + `${s[Math.floor(s.length * 0.1)].toFixed(3).padStart(7)}  `
        + `${s[Math.floor(s.length * 0.9)].toFixed(3).padStart(7)}  `
        + `${(rs.filter((x) => Math.abs(x - 1) <= 0.1).length / rs.length * 100)
            .toFixed(1).padStart(6)}%`);
};

console.log(`${rows.length} clean Single readings where the wire agrees\n`);
console.log("  OUR cycle life / THEIRS      n   median      p10      p90   within 10%");
show("all", rows);
show("the three sold IDs", rows.filter((x) => x.sold));

for (const id of [2.625, 3.75, 5.25]) {
    show(`  ${ID_TEXT[id]}`, rows.filter((x) => x.id === id));
}

console.log("\n  HOW MUCH MARGIN THE REFERENCE LEAVES over the cycle target");
console.log("  (the wire rule takes the softest candidate that reaches it, so");
console.log("   a reading with little margin is one our error can flip)\n");
console.log("  reference cycles / target     n");

for (const [lo, hi] of [[0, 1.1], [1.1, 1.25], [1.25, 1.5], [1.5, 2], [2, 1e9]]) {
    const g = rows.filter((x) => x.margin >= lo && x.margin < hi);

    console.log(`  ${`${lo} - ${hi === 1e9 ? "+" : hi}`.padEnd(28)}${String(g.length).padStart(4)}`
        + `   ${(g.length / rows.length * 100).toFixed(1)}%`);
}
