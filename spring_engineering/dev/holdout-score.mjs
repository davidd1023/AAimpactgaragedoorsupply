// Score ONLY the readings named on stdin as withheld (HELD<tab>key lines).
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
const mod = await load();
const want = new Set(
    readFileSync(0, "utf8").split("\n")
        .filter((l) => l.startsWith("HELD\t"))
        .map((l) => l.slice(5))
);
// SCORE_EXCLUDE=R1,U5 scores only readings OUTSIDE those batches.
//
// WHY THIS IS NEEDED. Moving a batch into or out of the fit changes what the
// holdout SCORES as well as what it fits, because a `fit: false` reading is
// still scored. A batch that is fitted gets same-batch neighbours in every
// fold, so it predicts better - and the overall figure rises even if nothing
// else got better. That is not a subtle effect: re-fitting U5-U8 raised this
// number by 0.88 points while the never-tuned validation sample FELL by 2.3.
//
// Excluding the toggled batch from the SCORING leaves a fixed population, which
// is the only way this number answers "does that data help other doors".
const exclude = (process.env.SCORE_EXCLUDE || "")
    .split(",").map((x) => x.trim()).filter(Boolean);
const c = JSON.parse(readFileSync("./dev/corpus.json", "utf8"));
let n = 0, wire = 0, len = 0, all = 0;
for (const r of c.readings) {
    if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) continue;
    if (exclude.some((p) => (r.id ?? "").startsWith(p + "-"))) continue;
    const st = r.state;
    const key = [st.drum, st.springs, st.radius, st.liftType ?? "Standard",
        st.liftin ?? "", st.cycles, st.weight, st.doorHeightFeet,
        st.doorHeightInches ?? 0].join("|");
    if (!want.has(key)) continue;
    const comp = make(mod, st);
    const s = comp.duplexStep;
    const refW = `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
    const wok = s && `${s.outerWire}/${s.innerWire}` === refW;
    const lok = wok && comp.duplexInnerLength === r.expect.duplexInnerLength;
    n += 1; wire += wok ? 1 : 0; len += lok ? 1 : 0; all += lok ? 1 : 0;
}
console.log(`  held out: ${n}   wire ${wire}/${n}   wire+length ${len}/${n}`);
