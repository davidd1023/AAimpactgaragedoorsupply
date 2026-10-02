// Per-drum accuracy and coverage. The whole-corpus number hides the drums:
// one drum held 1772 readings while another held 19, so "99%" said almost
// nothing about the thin ones. This reports each drum on its own, with the
// spread of every input that matters, so a drum with no failures and no
// coverage cannot pass for a verified drum.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";

const mod = await load();
const c = JSON.parse(readFileSync("./dev/corpus.json", "utf8"));
const per = new Map();

for (const r of c.readings) {
    if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) {
        continue;
    }

    const st = r.state;
    const comp = make(mod, st);
    const s = comp.duplexStep;
    const e = per.get(st.drum) ?? {
        n: 0, wire: 0, len: 0,
        w: new Set(), h: new Set(), cy: new Set(),
        sp: new Set(), rad: new Set(), hl: new Set(), fails: [],
    };

    const refW = `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
    const wok = s && `${s.outerWire}/${s.innerWire}` === refW;
    const lok = wok && comp.duplexInnerLength === r.expect.duplexInnerLength;

    e.n += 1;
    e.wire += wok ? 1 : 0;
    e.len += lok ? 1 : 0;
    e.w.add(Number(st.weight));
    e.h.add(Number(st.doorHeightFeet) * 12 + Number(st.doorHeightInches || 0));
    e.cy.add(st.cycles);
    e.sp.add(st.springs);
    e.rad.add(st.radius);

    if (st.liftType === "Hi-Lift") {
        e.hl.add(Number(st.liftin));
    }

    if (!lok) {
        e.fails.push(`${st.weight}lb ${st.doorHeightFeet}'${st.doorHeightInches || 0}" ` +
            `${st.springs}spr r${st.radius}${st.liftType === "Hi-Lift" ? ` hl${st.liftin}` : ""} ` +
            `t${st.cycles}  want ${refW} L ${r.expect.duplexInnerLength}, got ` +
            `${s ? `${s.outerWire}/${s.innerWire}` : "none"} L ${comp.duplexInnerLength}`);
    }

    per.set(st.drum, e);
}

const span = (set) => {
    const v = [...set].sort((a, b) => a - b);

    return v.length ? `${v[0]}-${v[v.length - 1]} (${v.length})` : "-";
};

console.log(
    "drum".padEnd(22) + "n".padStart(5) + "wire".padStart(10) + "wire+len".padStart(11) +
    "   weights".padEnd(20) + " heights".padEnd(16) + " tgts" + "  springs" + "  radii"
);

for (const [drum, e] of [...per].sort((a, b) => b[1].n - a[1].n)) {
    console.log(
        drum.split(" ").pop().padEnd(22) +
        String(e.n).padStart(5) +
        `${e.wire}/${e.n}`.padStart(10) +
        `${e.len}/${e.n}`.padStart(11) +
        "   " + span(e.w).padEnd(17) +
        " " + span(e.h).padEnd(15) +
        String(e.cy.size).padStart(5) +
        "  " + [...e.sp].sort().join(",").padEnd(7) +
        "  " + [...e.rad].sort().join(",")
    );
}

for (const [drum, e] of [...per].sort()) {
    if (!e.fails.length) continue;
    console.log(`\n${drum}  (${e.fails.length} failing)`);
    for (const f of e.fails.slice(0, 8)) console.log("   " + f);
    if (e.fails.length > 8) console.log(`   ... and ${e.fails.length - 8} more`);
}
