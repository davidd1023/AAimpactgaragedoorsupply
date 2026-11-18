// HOW ACCURATE IS THE CYCLE MODEL, AGAINST THE REFERENCE'S OWN FIGURE?
//
//   node dev/cycle-error.mjs
//
// THE ONE QUANTITY IN THIS ENGINE THAT HAS DIRECT SUPERVISION AND HAS NEVER
// BEEN FITTED. Every wire miss recorded in this project - 54 duplex and the
// one Single - is a threshold decision on cycle life:
//
//     take the softest candidate whose life reaches the target
//
// and the targets are FIXED CONSTANTS (10,000 / 25,000 / 50,000 / 100,000).
// That matters: in the LENGTH model the fitted slope `b` absorbs a scale
// error, which is why refitting the stiffness model changed nothing. Nothing
// absorbs an error here. A one per cent bias in the cycle model moves real
// decisions.
//
// AND THE REFERENCE REPORTS ITS CYCLE FIGURE in every response, so unlike
// length this can be measured directly rather than inferred. 6,932 readings
// across the pulled and eval files carry `data.cycles`. The corpus does not
// keep it, so the raw files are the source.
//
// THE MODEL IS THREE NUMBERS:
//
//     cyclesForWire(w) = ((COEFFICIENT * w^WIRE_EXPONENT) / torque) ^ EXPONENT
//     COEFFICIENT 124205   WIRE_EXPONENT 2.79   EXPONENT 4.67
//
// NON-CIRCULAR BY CONSTRUCTION: only readings where OUR wire already matches
// THEIRS are compared, so both figures describe the same spring. On a wire
// miss they describe two different springs and the comparison is meaningless -
// that mistake was made once already and nearly reported as a finding.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";
import { stateFromReading, isClean, REF_RADIUS } from "./ref-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};
const rows = [];

const files = readdirSync(HERE).filter((f) =>
    /^(pulled|eval-|biased).*\.json$/.test(f));

for (const file of files) {
    let data;

    try { data = JSON.parse(readFileSync(join(HERE, file), "utf8")); } catch { continue; }
    if (!Array.isArray(data)) continue;

    for (const r of data) {
        const i = r?.input, d = r?.data;
        const theirs = d?.cycles;

        if (!i || !d || !(theirs > 0)) continue;
        if (!isClean(r)) continue;            // flagged readings only muddy this

        const duplex = i.assembly === "Duplex";
        let c;

        if (duplex) {
            if (!d.outerSpring || !d.innerSpring) continue;

            try { c = make(mod, stateFromReading(i)); } catch { continue; }

            const step = c.duplexStep;

            if (!step) continue;

            // SAME SPRING ON BOTH SIDES, or the comparison is meaningless.
            if (step.outerWire !== parseFloat(d.outerSpring.wireSize)
                || step.innerWire !== parseFloat(d.innerSpring.wireSize)) {
                continue;
            }

            // `rounded` ROUNDS TIPPT AND TURNS TO ONE DECIMAL, which is
            // what the reference itself does before computing - not an output
            // rounding, which is what the flag name suggests and what I first
            // assumed. The engine's own comment says replicating it "nearly
            // doubled the exact matches". So the DEFAULT is the comparison to
            // make against a reported figure; `rounded: false` is the path the
            // wire DECISION uses, and both are measured below.
            const ours = c.duplexCyclesForStep(step);
            const oursRaw = c.duplexCyclesForStep(step, { rounded: false });

            if (!(ours > 0)) continue;

            rows.push({
                kind: "duplex",
                rung: `${step.outerWire}/${step.innerWire}`,
                wire: step.outerWire,
                target: Number(i.cycles),
                springs: c.duplexSpringCount,
                ours, oursRaw, theirs, ratio: ours / theirs,
            });
            continue;
        }

        const sp = d.outerSpring || d.innerSpring;
        const idText = ID_TEXT[Number(i.innerDiameter)];

        if (!sp?.wireSize || !idText || i.assembly !== "Single") continue;

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";

        try {
            c = make(mod, {
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
        } catch { continue; }

        if (c.recommendedWire === null
            || Math.abs(c.recommendedWire - sp.wireSize) > 1e-9) {
            continue;                          // wire miss - different springs
        }

        const ours = c.cyclesForWire(sp.wireSize);

        if (!(ours > 0)) continue;

        rows.push({
            kind: "single", rung: idText, wire: sp.wireSize,
            target: Number(i.cycles), springs: i.springs ?? 2,
            ours, oursRaw: ours, theirs, ratio: ours / theirs,
        });
    }
}

const q = (xs, p) => {
    const s = xs.slice().sort((a, b) => a - b);
    return s.length ? s[Math.min(s.length - 1, Math.floor(s.length * p))] : NaN;
};
const band = (xs) => `${q(xs, .1).toFixed(3)}  ${q(xs, .5).toFixed(3)}  `
    + `${q(xs, .9).toFixed(3)}`;
const within = (xs, f) => (xs.filter((x) => Math.abs(x - 1) <= f).length
    / xs.length * 100).toFixed(1);

console.log(`${rows.length} CLEAN readings where our wire already matches `
    + `the reference's\n`);
console.log("OUR cycle figure / THEIRS           p10    median    p90"
    + "    within 2%   within 5%");

const show = (label, set) => {
    if (set.length < 12) return;

    const rs = set.map((x) => x.ratio);

    console.log(`  ${label.padEnd(32)}${band(rs)}`
        + `${within(rs, .02).padStart(10)}%${within(rs, .05).padStart(10)}%`
        + `   n=${set.length}`);
};

show("ALL", rows);
console.log("");
show("Single", rows.filter((x) => x.kind === "single"));
show("Duplex", rows.filter((x) => x.kind === "duplex"));

console.log("\nBY CYCLE TARGET");
for (const t of [10000, 25000, 50000, 100000]) {
    show(`target ${t.toLocaleString("en-US")}`, rows.filter((x) => x.target === t));
}

console.log("\nBY WIRE SIZE  (the model is a power law in wire)");
for (const [lo, hi] of [[0, .25], [.25, .3], [.3, .35], [.35, .4],
    [.4, .47], [.47, .56], [.56, 1]]) {
    show(`wire ${lo}-${hi}`, rows.filter((x) => x.wire > lo && x.wire <= hi));
}

console.log("\nBY SPRING COUNT");
for (const n of [1, 2, 3, 4]) {
    show(`${n} spring(s)`, rows.filter((x) => x.springs === n));
}

// ---------------------------------------------------------------- ROUNDING
// EVERY ONE of the 6,923 reference cycle figures is a multiple of 1,000, and
// under 20,000 the distinct values are 9000, 10000, 11000 ... So at an
// 11,000-cycle answer the reference's own REPORTING granularity is +/-4.5%,
// which is the whole of the spread measured above - and a declining density
// of true values inside each bin biases the ratio upward, which is the whole
// of the apparent drift at target 10,000.
//
// So the honest comparison rounds OURS the same way before comparing.
console.log("\nTHE REFERENCE REPORTS ONLY MULTIPLES OF 1,000.");
console.log("Rounding ours the same way is the only fair comparison:\n");
console.log("  set                               exact match   within 1 step");

const rounded = (label, set) => {
    if (set.length < 12) return;

    const hit = set.filter((x) => Math.round(x.ours / 1000) * 1000 === x.theirs).length;
    const near = set.filter((x) =>
        Math.abs(Math.round(x.ours / 1000) * 1000 - x.theirs) <= 1000).length;

    console.log(`  ${label.padEnd(32)}`
        + `${(hit / set.length * 100).toFixed(1).padStart(8)}%`
        + `${(near / set.length * 100).toFixed(1).padStart(14)}%   n=${set.length}`);
};

rounded("ALL", rows);
rounded("Single", rows.filter((x) => x.kind === "single"));
rounded("Duplex", rows.filter((x) => x.kind === "duplex"));
for (const t of [10000, 25000, 50000, 100000]) {
    rounded(`target ${t.toLocaleString("en-US")}`, rows.filter((x) => x.target === t));
}

console.log("\n  A HIGH exact-match rate means the cycle model already agrees");
console.log("  with the reference to the precision the reference reports, and");
console.log("  there is nothing left to fit. The apparent 1.3% drift at the");
console.log("  10,000 target would then be the rounding, not the model.");

console.log("\nAND THE WIRE DECISION USES THE UNROUNDED FIGURE - does that");
console.log("agree with the reference as well?\n");
console.log("  set                               exact match   within 1 step");

const rawRounded = (label, set) => {
    if (set.length < 12) return;

    const hit = set.filter((x) =>
        Math.round(x.oursRaw / 1000) * 1000 === x.theirs).length;
    const near = set.filter((x) =>
        Math.abs(Math.round(x.oursRaw / 1000) * 1000 - x.theirs) <= 1000).length;

    console.log(`  ${label.padEnd(32)}`
        + `${(hit / set.length * 100).toFixed(1).padStart(8)}%`
        + `${(near / set.length * 100).toFixed(1).padStart(14)}%   n=${set.length}`);
};

rawRounded("Duplex, UNROUNDED tippt/turns", rows.filter((x) => x.kind === "duplex"));

console.log("\n  A LARGE gap between this and the rounded figure above means");
console.log("  the wire decision is taken on a quantity further from the");
console.log("  reference's than the displayed one is - which would be worth");
console.log("  fixing, because the decision is what picks the spring.");

console.log("\n  A FLAT median near 1.000 across every cut means the three");
console.log("  constants are already right and the spread is irreducible noise.");
console.log("  A median that DRIFTS with wire size means WIRE_EXPONENT is off;");
console.log("  one that drifts with target or spring count means something the");
console.log("  model does not see. Either of those is a fittable error, and");
console.log("  nothing in this engine absorbs it the way `b` absorbs length.");
