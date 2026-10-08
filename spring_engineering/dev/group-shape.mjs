// The shape of one (rung, spring count) group: what the reference's bonus does
// as a function of frac(active length), laid out by the integer part.
//
//   node dev/group-shape.mjs 0.289/0.2343 2
//
// WHY. The length rule is a function of frac, and the thresholds move with the
// integer part. Printed this way the structure is usually obvious - it is how
// the non-parallel thresholds on 0.2625/0.2253 at two springs were found, and
// those carried half the model's error.
import { load, make } from "./harness.mjs";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const [wantRung, wantSpr] = process.argv.slice(2);

if (!wantRung || !wantSpr) {
    console.error("usage: node dev/group-shape.mjs <outer>/<inner> <springs>");
    process.exit(1);
}

const mod = await load();
const rows = [];

for (const r of JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8")).readings) {
    if (r.status !== "verified" || !r.expect || r.expect.duplexInnerLength === undefined) continue;
    if (String(r.state.springs) !== String(wantSpr)) continue;

    const L = r.expect.duplexInnerLength;

    if (!(L > 0 && L <= 120)) continue;

    const rung = `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;

    if (rung !== wantRung) continue;

    const c = make(mod, r.state);
    const s = c.duplexStep;

    if (!s || `${s.outerWire}/${s.innerWire}` !== rung) continue;

    const x = c.duplexActiveLength;
    const n = Math.floor(x);

    rows.push({
        f: x - n, n, bonus: Number((L - n).toFixed(2)),
        ours: c.duplexInnerLength, ref: L,
        clean: (c.warnings ?? []).length === 0,
    });
}

if (!rows.length) {
    console.log("no readings for that group");
    process.exit(0);
}

const levels = new Map();

for (const r of rows) levels.set(r.bonus, (levels.get(r.bonus) || 0) + 1);

console.log(`${wantRung} at ${wantSpr} spring(s): ${rows.length} readings, ` +
    `${rows.filter((r) => r.ours !== r.ref).length} we get wrong`);
console.log("levels: " + [...levels].sort((a, b) => a[0] - b[0])
    .map(([k, v]) => `${k}:${v}`).join("  "));

const byFloor = new Map();

for (const r of rows) {
    if (!byFloor.has(r.n)) byFloor.set(r.n, []);
    byFloor.get(r.n).push(r);
}

const vals = [...levels.keys()].sort((a, b) => a - b);
const rng = (l) => l.length
    ? `${Math.min(...l.map((r) => r.f)).toFixed(2)}-${Math.max(...l.map((r) => r.f)).toFixed(2)}(${l.length})`
    : "-";

console.log("\nfrac range of each bonus level, by integer part:");
console.log("floor  " + vals.map((v) => `bonus ${v}`.padEnd(18)).join(""));

for (const [n, l] of [...byFloor].sort((a, b) => a[0] - b[0])) {
    if (l.length < 3) continue;

    const bad = l.filter((r) => r.ours !== r.ref).length;

    console.log(`${String(n).padStart(4)}   ` +
        vals.map((v) => rng(l.filter((r) => r.bonus === v)).padEnd(18)).join("") +
        (bad ? `  ${bad} wrong` : ""));
}
