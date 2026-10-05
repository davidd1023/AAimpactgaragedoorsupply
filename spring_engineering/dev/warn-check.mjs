// Compare the warnings WE raise against the messages the REFERENCE returned,
// reading by reading, across every pull.
//
// This is the only honest test of a warning. A warning cannot be checked by a
// snapshot of our own past behaviour, and it does not show up in the accuracy
// score at all - Duplex raised five warnings while the reference raised eleven
// and every number still matched.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };

// Which of our ids answers which reference message.
const MAP = [
    [/is over max MIP/i, "duplex-mip-over-max"],
    [/maximum for the inner spring inner diameter/i, "duplex-inner-wire-unsold"],
    [/maximum for the outer spring inner diameter/i, "duplex-outer-wire-unsold"],
    [/cycle life calculation of .* is less than/i, "duplex-cycles-low"],
    [/cycle life calculation of .* exceeds/i, "duplex-cycles-over-max"],
    [/Only spring lengths between/i, "duplex-length-unsupported"],
    [/too long for a .* wide door/i, "assembly-too-long"],
    [/height entered is greater than this drum/i, "height-over-max"],
    [/weight entered is heavier than this drum/i, "weight-over-max"],
];
const IGNORE = /Please contact us/i;

const tally = new Map();
const bump = (id, field) => {
    const e = tally.get(id) ?? { both: 0, refOnly: 0, oursOnly: 0 };
    e[field] += 1;
    tally.set(id, e);
};

for (const file of process.argv.slice(2)) {
    let rows;

    try {
        rows = JSON.parse(readFileSync(file, "utf8"));
    } catch {
        continue;
    }

    for (const r of rows) {
        const i = r.input;

        if (r.error || !r.data || (i.assembly ?? "Duplex") !== "Duplex") {
            continue;
        }

        if (Number(i.innerId) !== 3.75 || Number(i.outerId) !== 6) {
            continue;
        }

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
        const ours = new Set((c.warnings ?? []).map((w) => w.id));
        const refMsgs = (r.messages ?? []).filter((m) => !IGNORE.test(m));
        const refIds = new Set();

        for (const m of refMsgs) {
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
            else if (inOurs) bump(id, "oursOnly");
        }
    }
}

console.log("warning".padEnd(30) + "agree".padStart(7) + "ref only".padStart(10) + "ours only".padStart(11));
for (const [id, e] of [...tally].sort((a, b) => (b[1].both + b[1].refOnly) - (a[1].both + a[1].refOnly))) {
    if (!e.both && !e.refOnly && !e.oursOnly) continue;
    console.log(id.padEnd(30) + String(e.both).padStart(7) + String(e.refOnly).padStart(10) + String(e.oursOnly).padStart(11));
}
