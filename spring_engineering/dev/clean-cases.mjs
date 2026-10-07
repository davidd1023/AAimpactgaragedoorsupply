// Accuracy on the readings the reference answers WITHOUT complaint.
//
// These matter most: a door the reference quotes cleanly is a door that gets
// ordered. A warning at least makes someone look. So this splits the external
// samples into clean and flagged, and scores them separately.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { stateFromReading, isHiLift, isClean, isModelledDuplex } from "./ref-state.mjs";

const mod = await load();
const bucket = { clean: { n: 0, wire: 0, len: 0, in1: 0 },
                 flagged: { n: 0, wire: 0, len: 0, in1: 0 } };
const misses = [];

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

        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(m));
        const which = msgs.length === 0 && r.status === "success" ? "clean" : "flagged";
        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, stateFromReading(i));
        const s = c.duplexStep;

        if (!s) continue;

        const b = bucket[which];
        const refW = `${r.data.outerSpring.wireSize}/${r.data.innerSpring.wireSize}`;
        const wok = `${s.outerWire}/${s.innerWire}` === refW;
        const d = c.duplexInnerLength - r.data.innerSpring.springLength;

        b.n += 1;
        b.wire += wok ? 1 : 0;
        b.len += wok && d === 0 ? 1 : 0;
        b.in1 += wok && Math.abs(d) <= 1 ? 1 : 0;

        if (which === "clean" && !(wok && d === 0)) {
            misses.push(
                `   ${i.drum.split(" ").pop().padEnd(10)} ${String(i.weight).padStart(5)}lb ` +
                `${Math.floor(i.heightInches / 12)}'${i.heightInches % 12}" ${i.springs}spr ` +
                `r${i.radius}${hi ? ` hl${i.hiLift}` : ""} t${i.cycles}  ` +
                `ref ${refW} ${r.data.innerSpring.springLength}"  ` +
                `ours ${s.outerWire}/${s.innerWire} ${c.duplexInnerLength}"`
            );
        }
    }
}

for (const [k, b] of Object.entries(bucket)) {
    if (!b.n) continue;
    const p = (x) => `${(x / b.n * 100).toFixed(1)}%`;
    console.log(`${k.toUpperCase().padEnd(8)} ${String(b.n).padStart(4)} readings   ` +
        `wire ${p(b.wire)}   length ${p(b.len)}   within 1" ${p(b.in1)}`);
}

if (misses.length) {
    console.log(`\nthe ${misses.length} CLEAN readings we get wrong:`);
    console.log(misses.slice(0, 25).join("\n"));
    if (misses.length > 25) console.log(`   ... and ${misses.length - 25} more`);
}
