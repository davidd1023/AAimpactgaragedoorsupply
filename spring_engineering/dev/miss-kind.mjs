// WHAT KIND OF WRONG IS EACH LENGTH MISS?
//
//   node dev/miss-kind.mjs dev/eval-validation-seed61006.json [more samples...]
//
// Every length miss is one of two things, and they have different fixes:
//
//   PLACEMENT - the group's rule can produce the bonus the reference used, and
//   put the boundary on the wrong side of this reading. The rule is right and
//   its threshold is a hair off. More parameters cannot help; only a better
//   placement of the same line, or readings that pin it more finely.
//
//   MISSING LEVEL - the rule cannot produce that bonus at all, because the
//   fitting data for that (rung, spring count) never showed it. No amount of
//   threshold work fixes this one; the group needs the level.
//
// Knowing the split is what stops the next idea being wasted. Measured over the
// four external samples it is 13 placement to 3 missing, so the length rule is
// limited by where its boundaries sit and not by what they choose between -
// which is why maximising the margin of each threshold line bought 1.2 points
// and why adding levels would buy at most 0.5.
//
// All three missing-level cases want a bonus the SAME RUNG already uses at
// another spring count, so the level is known to be real and only its
// applicability to that count is unobserved. That is the one place borrowing
// structure across spring counts has any evidence behind it.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { stateFromReading, isClean, isModelledDuplex } from "./ref-state.mjs";

const mod = await load();
const out = [];

for (const f of process.argv.slice(2)) {
    let data;
    try { data = JSON.parse(readFileSync(f, "utf8")); } catch { continue; }
    for (const r of data) {
        const i = r.input;
        if (r.error || !r.data?.innerSpring || !isModelledDuplex(i) || !isClean(r)) continue;
        const c = make(mod, stateFromReading(i));
        const s = c.duplexStep;
        if (!s) continue;
        if (s.innerWire !== r.data.innerSpring.wireSize
            || s.outerWire !== r.data.outerSpring.wireSize) continue;
        const ours = c.duplexInnerLength, want = r.data.innerSpring.springLength;
        if (ours === want) continue;
        const al = c.duplexActiveLength;
        const whole = Math.floor(al);
        const need = Math.round((want - whole) * 100) / 100;
        const sp = i.springs;
        const split = s.splitByCount && s.splitByCount[sp];
        const line = split ? (Math.floor(al) >= split.from ? split.above : split.below)
                           : (s.lineByCount && s.lineByCount[sp]);
        let levels = null;
        if (line) {
            if (line.levels) levels = line.levels.slice();
            else if (line.mid !== undefined) levels = [line.lo, line.mid, line.hi];
            else levels = [line.lo, line.hi];
        } else if (s.byCount && s.byCount[sp]) {
            levels = [...new Set(s.byCount[sp].map((b) => b.bonus))];
        }
        // Levels across the WHOLE rung, every spring count - what the rung is
        // known to be capable of, as opposed to what this group observed.
        const rungLevels = new Set();
        for (const tbl of [s.lineByCount, s.splitByCount]) {
            for (const k of Object.keys(tbl ?? {})) {
                const l = tbl[k];
                for (const side of (l.below || l.above) ? [l.below, l.above] : [l]) {
                    if (!side) continue;
                    if (side.levels) side.levels.forEach((v) => rungLevels.add(v));
                    else { rungLevels.add(side.lo); if (side.mid !== undefined) rungLevels.add(side.mid); rungLevels.add(side.hi); }
                }
            }
        }
        for (const k of Object.keys(s.byCount ?? {})) {
            for (const b of s.byCount[k]) rungLevels.add(b.bonus);
        }
        out.push({
            rung: `${s.outerWire}/${s.innerWire}`, sp, need,
            levels, hasIt: levels ? levels.some((v) => Math.abs(v - need) < 1e-9) : null,
            inRung: rungLevels.has(need),
            d: ours - want,
        });
    }
}

const missing = out.filter((r) => r.hasIt === false);
console.log(`${out.length} clean misses across the samples\n`);
console.log(`  needing a level the group's rule HAS (boundary placement): ${out.filter((r) => r.hasIt === true).length}`);
console.log(`  needing a level it does NOT have (missing level):          ${missing.length}`);
console.log(`  on the grid default, so no rule at all:                    ${out.filter((r) => r.hasIt === null).length}`);
console.log(`\n  of the missing-level misses, how many want a level the RUNG`);
console.log(`  already uses at another spring count: ${missing.filter((r) => r.inRung).length} of ${missing.length}`);
console.log("\ndetail:");
for (const r of out) {
    console.log(`  ${r.rung.padEnd(16)} ${r.sp}spr  needed ${String(r.need).padStart(6)}`
        + `  rule has [${(r.levels ?? []).join(", ")}]`
        + `  ${r.hasIt === false ? (r.inRung ? "MISSING (rung knows it)" : "MISSING (new to the rung)") : r.hasIt === null ? "no rule" : "placement"}`);
}
