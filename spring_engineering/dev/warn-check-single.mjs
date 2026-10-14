// Compare the warnings WE raise on the SINGLE path against the messages the
// REFERENCE returned, reading by reading.
//
// warn-check.mjs does this for Duplex and skips everything else, so the Single
// warnings have never been measured against anything - which is how a false
// alarm on hi-lift survived: the owner met it on the shop page, not here.
//
// TWO READINGS OF THE SAME DATA, because a disagreement has two possible
// causes and they need different fixes:
//
//   default      our own wire choice - what somebody using the page sees.
//   --ref-wire   the reference's own wire fed back in. A warning that
//                disagrees here is the RULE being wrong; one that disagrees
//                only in the first mode is the WIRE being different.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const ID_TEXT = {
    1.75: '1 3/4"', 2.625: '2 5/8"', 3.75: '3 3/4"',
    4.375: '4 3/8"', 5.25: '5 1/4"', 6: '6"',
};

// Which of our ids answers which reference message. The reference says "outer
// spring inner diameter" even when it is quoting a single spring.
const MAP = [
    [/wire size exceeds .* maximum for the outer spring inner diameter/i, "wire-over-max"],
    [/wire size exceeds .* maximum for this i\.?d/i, "wire-over-max"],
    // THE REFERENCE'S OWN WORDING, not ours. It says "does not meet ...
    // minimum"; we say "is less than the minimum". Matching on our phrasing
    // scored 0 agreements and 26 false alarms against a rule that was in fact
    // right every time - a bug in the measuring tool reading as a bug in the
    // thing measured, which is the one failure a tool like this must not have.
    [/wire size does not meet .* minimum/i, "wire-under-min"],
    [/wire size is less than the minimum/i, "wire-under-min"],
    [/out of bounds cycle count/i, "cycles-over-max"],
    [/cycle life calculation of .* is less than/i, "cycles-low"],
    [/low cycle life/i, "cycles-low"],
    [/too long for a .* wide door/i, "assembly-too-long"],
    [/height entered is greater than this drum/i, "height-over-max"],
    [/weight entered is heavier than this drum/i, "weight-over-max"],
    [/greater than the maximum allowed/i, "hilift-over-max"],
];
// Said on 23 readings here and deliberately not modelled - see the note on
// DUPLEX_MAX_SPRING_LENGTH in the source. Not counted either way.
const UNMODELLED = [
    /only spring lengths between .* are recommended/i,
    /only spring lengths between .* are supported/i,
    /please contact us/i,
];

const refWire = process.argv.includes("--ref-wire");
const files = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const tally = new Map();
const examples = new Map();
let read = 0;

const bump = (id, field, row) => {
    const e = tally.get(id) ?? { both: 0, refOnly: 0, oursOnly: 0 };
    e[field] += 1;
    tally.set(id, e);

    if (field === "oursOnly" && row) {
        const list = examples.get(id) ?? [];

        if (list.length < 4) {
            list.push(row);
            examples.set(id, list);
        }
    }
};

for (const file of files) {
    let rows;

    try {
        rows = JSON.parse(readFileSync(file, "utf8"));
    } catch {
        continue;
    }

    for (const r of rows) {
        const i = r.input ?? {};

        if (r.error || !r.data || (i.assembly ?? "Duplex") !== "Single") {
            continue;
        }

        const sp = r.data.innerSpring ?? r.data.outerSpring;

        if (!sp || !sp.springLength || !ID_TEXT[sp.innerDiameter]) {
            continue;
        }

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const state = {
            assembly: "Single",
            drum: i.drum,
            springId: ID_TEXT[sp.innerDiameter],
            springs: i.springs ?? 1,
            radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"),
            weight: String(i.weight),
            doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
            doorWidthInches: (i.widthInches ?? 108) % 12,
            doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        };

        if (refWire) {
            state.wireSize = `${sp.wireSize}"`;
        }

        const c = make(mod, state);

        if (!refWire) {
            // What the page does for itself before it warns.
            const pick = c.recommendedWire;

            if (pick !== null) {
                c.state.wireSize = `${pick}"`;
            }
        }

        read += 1;

        const ours = new Set((c.warnings ?? []).map((w) => w.id));
        const refIds = new Set();

        for (const m of r.messages ?? []) {
            if (UNMODELLED.some((re) => re.test(m))) {
                continue;
            }

            const hit = MAP.find(([re]) => re.test(m));

            if (hit) {
                refIds.add(hit[1]);
            }
        }

        for (const [, id] of MAP) {
            const inRef = refIds.has(id);
            const inOurs = ours.has(id);

            if (inRef && inOurs) bump(id, "both");
            else if (inRef) bump(id, "refOnly");
            else if (inOurs) bump(id, "oursOnly", { ...i, wire: c.state.wireSize });
        }
    }
}

console.log(`${read} Single readings, wire = ${refWire ? "the reference's" : "ours"}\n`);
console.log("warning".padEnd(22) + "agree".padStart(7) + "ref only".padStart(10) + "ours only".padStart(11));

for (const [id, e] of [...tally].sort((a, b) => b[1].oursOnly - a[1].oursOnly)) {
    if (!e.both && !e.refOnly && !e.oursOnly) continue;
    console.log(id.padEnd(22) + String(e.both).padStart(7) + String(e.refOnly).padStart(10) + String(e.oursOnly).padStart(11));
}

for (const [id, list] of examples) {
    console.log(`\n${id} - we warn, the reference does not:`);
    for (const x of list) {
        console.log("   " + JSON.stringify(x));
    }
}
