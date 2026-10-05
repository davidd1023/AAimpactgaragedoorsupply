// For every failing length, show the active length and the bonus the reference
// implies, next to the PASSING readings on the same (rung, spring count). If
// frac alone decided the length, a failing reading would have to share a frac
// band with a passing one that wants a different bonus. If instead the
// failures separate by active length, the rule needs a magnitude term.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
const mod = await load();
const c = JSON.parse(readFileSync("./dev/corpus.json", "utf8"));
const rows = [];
for (const r of c.readings) {
    if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) continue;
    const comp = make(mod, r.state);
    const step = comp.duplexStep;
    if (!step) continue;
    const refW = `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
    if (`${step.outerWire}/${step.innerWire}` !== refW) continue;   // wire-only misses excluded
    const act = comp.duplexActiveLength;
    rows.push({
        rung: refW, spr: comp.duplexSpringCount, act,
        frac: act - Math.floor(act),
        refL: r.expect.duplexInnerLength, ourL: comp.duplexInnerLength,
        bonus: r.expect.duplexInnerLength - Math.floor(act),
        ok: comp.duplexInnerLength === r.expect.duplexInnerLength,
    });
}
const bad = rows.filter((r) => !r.ok);
const keys = [...new Set(bad.map((r) => `${r.rung}|${r.spr}`))];
for (const k of keys) {
    const [rung, spr] = k.split("|");
    const mine = rows.filter((r) => r.rung === rung && r.spr === Number(spr));
    console.log(`\n${rung}  ${spr} spring(s)   ${mine.length} readings, ${mine.filter(r=>!r.ok).length} failing`);
    console.log("   active    frac   refL   ourL  bonus");
    for (const r of mine.slice().sort((a, b) => a.frac - b.frac)) {
        const near = mine.some((o) => o.ok !== r.ok && Math.abs(o.frac - r.frac) < 0.02 && o.bonus !== r.bonus);
        console.log(`   ${r.act.toFixed(3).padStart(8)} ${r.frac.toFixed(3)} ${String(r.refL).padStart(6)} ${String(r.ourL).padStart(6)} ${String(r.bonus).padStart(6)}  ${r.ok ? "" : "FAIL"}${near ? "  <- frac collides with a passing reading wanting a different bonus" : ""}`);
    }
}
