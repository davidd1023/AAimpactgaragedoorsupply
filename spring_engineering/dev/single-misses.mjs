// NAME EVERY CLEAN SINGLE READING THE MODEL GETS WRONG.
//
//   node dev/single-misses.mjs [eval files ...]
//
// Single measures 99.9% over 1,187 clean readings on the three sold I.D.s -
// which is one miss, and "is it 100%" cannot be answered by a percentage.
// This prints the readings themselves, with every input, so the question
// becomes "is this one fixable" rather than "how big is the number".
//
// THE EXTRACTION IS COPIED FROM dev/single-breakdown.mjs, DELIBERATELY. Three
// separate diagnostics in this project have reported zero rows by inventing
// field names - `i.springId`, `c.singleWireSize`, and reading `duplexCycles`
// as a number when it returns "48,000". The rule written down after the third
// is that a tool measuring what another tool already reports must share its
// extraction or be checked against it. This shares it.
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
    console.error("usage: node dev/single-misses.mjs <eval files ...>");
    process.exit(1);
}

const misses = [];
let clean = 0;

for (const file of files) {
    let data;

    try { data = JSON.parse(readFileSync(file, "utf8")); } catch { continue; }

    for (const r of data) {
        const i = r.input, d = r.data;
        const sp = d?.outerSpring || d?.innerSpring;

        if (r.error || !sp?.wireSize || !sp.springLength || !i?.innerDiameter) continue;
        if (i.assembly !== "Single") continue;

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";

        if (i.lift && !hi && i.lift !== "Standard") continue;

        const idText = ID_TEXT[Number(i.innerDiameter)];

        if (!idText) continue;

        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(String(m)));

        if (msgs.length || r.status !== "success") continue;   // clean only

        clean++;

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

        // BOTH CANDIDATES' CYCLE LIVES, TAKEN BEFORE ANYTHING IS MUTATED, and
        // through `cyclesForWire` rather than `cycleLife`.
        //
        // THIS LINE USED TO READ `c.cycleLife` AFTER the overwrite below, and
        // it cost a whole session. `cycleLife` reads `state.wireSize`, so once
        // that holds the REFERENCE's wire the getter reports the right figure
        // for the wrong spring - 16,459 for 0.3065 where the question was
        // about 0.295. I compared it against the reference's 11,000 for 0.295
        // at the neighbouring weight, called it a 50% discrepancy, and wrote
        // an "unexplained anomaly" into CLAUDE.md as a thread to pick up.
        // There was nothing there.
        //
        // The fourth mistake of this family: `i.springId`, `c.singleWireSize`,
        // `duplexCycles` returning "48,000", and now a getter read after its
        // own inputs were changed underneath it. **Capture before mutating,
        // and name the wire you asked about.**
        const target = Number(i.cycles);
        const cycOurs = ourWire ? c.cyclesForWire(ourWire) : null;
        const cycTheirs = c.cyclesForWire(sp.wireSize);

        // The reference's own wire goes back in before length and weight are
        // compared, or a wire miss is counted three times over.
        c.state.wireSize = `${sp.wireSize}"`;

        const lenOk = c.springLength === sp.springLength;
        const wtOk = Math.abs(c.springWeight - sp.springWeight) < 0.02;

        if (wireOk && lenOk && wtOk) continue;

        misses.push({
            file: file.split("/").pop(), sold: SOLD.has(Number(i.innerDiameter)),
            id: idText, drum: (i.drum || "?").split(" ").pop(),
            springs: i.springs ?? 2, radius: i.radius, cycles: Number(i.cycles),
            lift: hi ? `HiLift ${i.hiLift}` : "Standard",
            door: `${(i.widthInches ?? 108) / 12}x${(i.heightInches / 12).toFixed(2)}`,
            h: i.heightInches, w: i.weight,
            wire: wireOk ? "ok" : `${ourWire} vs ${sp.wireSize}`,
            len: lenOk ? "ok" : `${c.springLength} vs ${sp.springLength}`,
            wt: wtOk ? "ok" : `${c.springWeight?.toFixed(2)} vs ${sp.springWeight?.toFixed(2)}`,
            // HOW CLOSE THE DECISION WAS. A wire miss on a door sitting on the
            // cycle-life threshold is a rounding fight, not a rule fault - the
            // duplex wire work established that and it is the first thing to
            // ask of any new one. The MARGIN is the number that answers it:
            // our chosen wire's life over the target, where 1.000 means the
            // door sat exactly on the line and no model could be asked to
            // sort it.
            target,
            cycOurs: cycOurs ? Math.round(cycOurs) : null,
            cycTheirs: cycTheirs ? Math.round(cycTheirs) : null,
            margin: cycOurs && target ? cycOurs / target : null,
        });
    }
}

console.log(`${clean} clean Single readings, ${misses.length} wrong\n`);

for (const m of misses) {
    console.log(`${m.sold ? "SOLD " : "     "}${m.id.padEnd(8)} ${m.drum.padEnd(9)}`
        + ` ${m.springs}spr r${String(m.radius).padEnd(3)} ${String(m.cycles).padStart(7)}cyc`
        + ` ${m.lift.padEnd(12)} door ${m.door.padEnd(10)} ${String(m.w).padStart(5)}lb`);
    console.log(`      wire ${m.wire}   length ${m.len}   weight ${m.wt}`);
    console.log(`      target ${m.target.toLocaleString("en-US")} cycles; `
        + `our life on OUR wire ${m.cycOurs?.toLocaleString("en-US")}`
        + ` (margin ${m.margin?.toFixed(3)}), on THEIRS `
        + `${m.cycTheirs?.toLocaleString("en-US")}`);
    console.log(`      (${m.file})`);
}

if (!misses.length) {
    console.log("  NOTHING. Every clean Single reading is exact on wire, "
        + "length and weight.");
}
