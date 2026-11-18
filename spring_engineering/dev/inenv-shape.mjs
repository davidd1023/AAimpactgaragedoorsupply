// The twelfth-form method, pointed IN-ENVELOPE. Past 120" the residual turned
// out to be two levels an inch apart that the clamped line could not express.
// Ask the same question of the band that actually matters (98.20%, 11,839
// readings): do the FAILING groups want more levels than the form allows, or
// is something else going on?
import { readFileSync } from "node:fs";
import { load, make } from "./harness.mjs";
const D = new URL(".", import.meta.url).pathname;
const mod = await load();
const corpus = JSON.parse(readFileSync(D + "corpus.json", "utf8"));
const g = new Map();
for (const r of corpus.readings) {
  if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) continue;
  let c; try { c = make(mod, r.state); } catch { continue; }
  const s = c.duplexStep; if (!s) continue;
  const rung = `${s.outerWire}/${s.innerWire}`;
  const wireOk = rung === `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
  if (!wireOk) continue;                       // a wire miss is a different spring
  const refMax = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);
  if (refMax > 96) continue;                   // THE RECOMMENDED BAND ONLY
  const act = c.duplexActiveLength, floor = Math.floor(act);
  const key = `${rung}|${c.duplexSpringCount}`;
  if (!g.has(key)) g.set(key, []);
  g.get(key).push({ floor, frac: +(act - floor).toFixed(3),
    level: r.expect.duplexInnerLength - floor,
    ok: c.duplexInnerLength === r.expect.duplexInnerLength
      && c.duplexOuterLength === r.expect.duplexOuterLength });
}
const rows = [...g].map(([k, v]) => [k, v]).filter(([, v]) => v.some((x) => !x.ok));
console.log(`${rows.length} in-envelope groups carry at least one failure\n`);
console.log("  group                      n  fails   levels (bonus:count)");
let lv2 = 0, lv3 = 0, lvMany = 0, f2 = 0, f3 = 0, fMany = 0;
for (const [k, v] of rows.sort((a,b)=>b[1].filter(x=>!x.ok).length - a[1].filter(x=>!x.ok).length)) {
  const h = new Map(); for (const x of v) h.set(x.level, (h.get(x.level) ?? 0) + 1);
  const lv = [...h].sort((a, b) => a[0] - b[0]);
  const bad = v.filter((x) => !x.ok).length;
  // count levels carrying real support - a single reading is noise, not a level
  const solid = lv.filter(([, n]) => n >= 2).length;
  if (solid <= 2) { lv2++; f2 += bad; } else if (solid === 3) { lv3++; f3 += bad; } else { lvMany++; fMany += bad; }
  if (bad >= 3) {
    const [rung, spr] = k.split("|");
    console.log(`  ${`${rung} ${spr}spr`.padEnd(24)}${String(v.length).padStart(4)}`
      + `${String(bad).padStart(6)}   ${lv.map(([a, n]) => `${a}:${n}`).join("  ")}`);
  }
}
console.log(`\n  LEVELS WITH REAL SUPPORT (>=2 readings), and the failures they carry:`);
console.log(`    <=2 levels   ${String(lv2).padStart(3)} groups   ${f2} failures`
  + "   <- the form ALLOWS two; these are NOT capacity");
console.log(`      3 levels   ${String(lv3).padStart(3)} groups   ${f3} failures`);
console.log(`     4+ levels   ${String(lvMany).padStart(3)} groups   ${fMany} failures`
  + "   <- capacity, already tested and lost");
console.log("\n  If most failures sit in groups of TWO levels, the form is not the");
console.log("  limit and the SEPARATOR or the fit's own gates are - which is a");
console.log("  knob sweep, not a rewrite. If they sit in 4+, it is capacity and");
console.log("  that experiment has already been run twice and lost.");
