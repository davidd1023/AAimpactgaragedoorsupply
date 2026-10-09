// The SINGLE path, sliced every way a customer can change the inputs.
//
//   node dev/single-breakdown.mjs [eval-single.json ...]
//
// WHY A BREAKDOWN AND NOT A SCORE. dev/single-external.mjs prints one figure
// for the whole sample, and one figure cannot tell "right everywhere" from
// "right on the 136 short standard-lift doors that happen to dominate the
// draw". The owner asked precisely that question - how close is each drum, how
// close is each spring count, radius, hi-lift, height - and the answer is a
// table, not a percentage.
//
// READ THE n COLUMN BEFORE THE PERCENTAGES. 100% of 6 readings and 100% of 60
// readings print identically here and mean very different things. Any slice
// under about 30 has a margin of ten points or worse.
//
// LENGTH IS SCORED ON THE REFERENCE'S OWN WIRE. Length follows from wire, so
// scoring our length against our own wire choice counts a single wire miss
// twice and makes the length column look worse than the model is. Whether we
// would have PICKED that wire is the separate `wire` column.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { REF_RADIUS } from "./ref-state.mjs";

const mod = await load();

// The spring ID as the DROPDOWN spells it. The component parses a decimal
// spelling such as `2.625"` perfectly well for every number it computes, so
// both spellings give the same wire, length and weight - but `WIRE_LIMITS` is
// keyed by this text, and only this text reaches the over-max/under-min
// warnings. Use the spelling a user can actually produce; a harness that feeds
// the app something its own UI cannot emit has been wrong here before.
const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};
// CLAUDE.md: only these three are offered to the customer.
const SOLD = new Set([2.625, 3.75, 5.25]);
const files = process.argv.slice(2);

if (!files.length) {
    files.push("./dev/eval-single.json");
}

const rows = [];

for (const file of files) {
    let data;

    try {
        data = JSON.parse(readFileSync(file, "utf8"));
    } catch {
        console.error(`skipping ${file} - unreadable`);
        continue;
    }

    for (const r of data) {
        const i = r.input, d = r.data;
        const sp = d?.outerSpring || d?.innerSpring;

        if (r.error || !sp?.wireSize || !sp.springLength || !i?.innerDiameter) continue;
        if (i.assembly !== "Single") continue;

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";

        if (i.lift && !hi && i.lift !== "Standard") continue;

        const idText = ID_TEXT[Number(i.innerDiameter)];

        if (!idText) continue;

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
        const ourWire = c.recommendedWire;
        const wireOk = ourWire !== null && Math.abs(ourWire - sp.wireSize) < 1e-9;

        // Feed the reference's wire back before measuring length and weight.
        c.state.wireSize = `${sp.wireSize}"`;

        const dLen = c.springLength - sp.springLength;
        // "contact us at 833-..." rides along with every other message and is
        // not itself a complaint about the inputs.
        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(String(m)));

        rows.push({
            clean: msgs.length === 0 && r.status === "success",
            wireOk, exact: dLen === 0, within1: Math.abs(dLen) <= 1,
            weightOk: Math.abs(c.springWeight - sp.springWeight) < 0.02,
            id: Number(i.innerDiameter), sold: SOLD.has(Number(i.innerDiameter)),
            drum: (i.drum || "?").split(" ").pop(), springs: i.springs ?? 2,
            cycles: Number(i.cycles), radius: Number(i.radius),
            hi, hiLift: i.hiLift, height: i.heightInches,
        });
    }
}

const pct = (a, b) => (b ? `${(100 * a / b).toFixed(1)}%` : "  -  ");
// Wilson half-width, so a thin slice carries its own warning instead of
// relying on the reader to check the n column.
function margin(a, b) {
    if (!b) return "";

    const p = a / b, z = 1.96, d = 1 + z * z / b;
    const half = z * Math.sqrt(p * (1 - p) / b + z * z / (4 * b * b)) / d;

    return `+-${(half * 100).toFixed(1)}`;
}

function table(title, rs, keyOf, order) {
    const by = new Map();

    for (const r of rs) {
        const k = keyOf(r);

        if (k === undefined || k === null) continue;
        if (!by.has(k)) by.set(k, []);

        by.get(k).push(r);
    }

    console.log(`\n${title}`);
    console.log('    slice                  n    wire   length  within 1"  weight   len +-');

    for (const k of (order ? [...by.keys()].sort(order) : [...by.keys()].sort())) {
        const v = by.get(k);
        const ex = v.filter((x) => x.exact).length;

        console.log(`    ${String(k).padEnd(21)}${String(v.length).padStart(4)}  `
            + `${pct(v.filter((x) => x.wireOk).length, v.length).padStart(6)}  `
            + `${pct(ex, v.length).padStart(6)}  `
            + `${pct(v.filter((x) => x.within1).length, v.length).padStart(7)}  `
            + `${pct(v.filter((x) => x.weightOk).length, v.length).padStart(7)}  `
            + `${margin(ex, v.length).padStart(7)}`);
    }
}

const clean = rows.filter((r) => r.clean);

console.log("=".repeat(80));
console.log(`SINGLE - ${files.map((f) => f.split("/").pop()).join(", ")}`);
console.log(`${rows.length} readings, ${clean.length} CLEAN (the reference raised no`);
console.log("complaint about the inputs). Only clean readings are sliced below.");
console.log("=".repeat(80));

const num = (a, b) => a - b;

table("ALL CLEAN READINGS", clean, () => "every slice pooled");
table("by spring ID", clean, (r) => `${ID_TEXT[r.id]}${r.sold ? "  (sold)" : ""}`);
table("the three IDs sold, pooled", clean.filter((r) => r.sold), () => "2 5/8 + 3 3/4 + 5 1/4");
table("by drum", clean, (r) => r.drum);
table("by spring count", clean, (r) => `${r.springs} spring${r.springs > 1 ? "s" : ""}`);
table("by cycle target", clean, (r) => r.cycles, num);
table("by track radius", clean, (r) => REF_RADIUS[r.radius] ?? r.radius);
table("by lift type", clean, (r) => (r.hi ? "hi-lift" : "standard"));
table("by hi-lift amount", clean.filter((r) => r.hi), (r) => {
    const lo = Math.floor(r.hiLift / 24) * 24;

    return `${String(lo).padStart(3)}-${lo + 23}"`;
});
table("by door height", clean, (r) => {
    const ft = Math.floor(r.height / 12), lo = Math.floor(ft / 3) * 3;

    return `${String(lo).padStart(2)}-${lo + 2} ft`;
}, (a, b) => parseInt(a, 10) - parseInt(b, 10));
