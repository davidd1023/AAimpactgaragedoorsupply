// Where the remaining length errors live, by (rung, spring count).
//
//   node dev/miss-profile.mjs [--targets N]
//
// WHY. The length model is fitted per rung and per spring count, so that is
// the grain at which it can be improved - and the errors are not spread
// evenly across it. Knowing which groups carry them is what turns "the model
// is 95% right" into a batch of readings worth taking. With --targets it
// prints the next groups as arguments for dev/frac-walk.mjs.
//
// Scored on the CLEAN external readings only: those are the doors the
// reference quotes without complaint, which are the ones that get ordered.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const wantTargets = process.argv.includes("--targets");
const nTargets = Number(process.argv[process.argv.indexOf("--targets") + 1]) || 11;
const g = new Map();

for (const f of readdirSync(HERE).filter((x) => /^eval.*\.json$/.test(x))) {
    let rows;

    try {
        rows = JSON.parse(readFileSync(join(HERE, f), "utf8"));
    } catch {
        continue;
    }

    for (const r of rows) {
        const i = r.input;

        if (!i || r.error || !r.data || !r.data.innerSpring) continue;
        if ((i.assembly ?? "Duplex") !== "Duplex" || Number(i.innerId) !== 3.75) continue;

        const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(m));

        if (msgs.length || r.status !== "success") continue;

        const hi = i.lift === "HiLift" || i.lift === "Hi-Lift";
        const c = make(mod, {
            assembly: "Duplex", drum: i.drum, springId: '3 3/4" inside 6"',
            springs: i.springs, radius: REF_RADIUS[Number(i.radius)] ?? String(i.radius),
            ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
            cycles: Number(i.cycles).toLocaleString("en-US"), weight: String(i.weight),
            doorWidthFeet: 18, doorHeightFeet: Math.floor(i.heightInches / 12),
            doorHeightInches: i.heightInches % 12,
        });
        const s = c.duplexStep;

        if (!s) continue;

        const rung = `${r.data.outerSpring.wireSize}/${r.data.innerSpring.wireSize}`;

        if (`${s.outerWire}/${s.innerWire}` !== rung) continue;

        const k = `${rung}|${i.springs}`;

        if (!g.has(k)) g.set(k, { n: 0, bad: 0 });

        const e = g.get(k);

        e.n += 1;
        e.bad += c.duplexInnerLength === r.data.innerSpring.springLength ? 0 : 1;
    }
}

const rows = [...g].map(([k, v]) => ({ k, ...v }));

rows.sort((a, b) => (b.bad * 100 + b.n) - (a.bad * 100 + a.n));

const tot = rows.reduce((a, r) => a + r.n, 0);
const bad = rows.reduce((a, r) => a + r.bad, 0);

if (wantTargets) {
    // Groups still carrying a miss, worst first, then the most-seen ones - a
    // group nobody hits is not worth a batch however wrong it is.
    const pick = rows.filter((r) => r.bad > 0).slice(0, nTargets);
    const fill = rows.filter((r) => !r.bad && r.n >= 8).slice(0, nTargets - pick.length);

    console.log([...pick, ...fill].map((r) => `'${r.k}'`).join(" "));
} else {
    console.log(`clean external readings with the rung right: ${tot}, length wrong on ${bad}`);
    console.log(`groups: ${rows.length}, carrying a miss: ${rows.filter((r) => r.bad).length}\n`);
    console.log("rung | springs      seen  misses  accuracy");

    for (const r of rows) {
        if (!r.bad && r.n < 8) continue;

        console.log(
            `${r.k.padEnd(22)} ${String(r.n).padStart(4)} ${String(r.bad).padStart(7)}` +
            `    ${(100 * (r.n - r.bad) / r.n).toFixed(0)}%`
        );
    }
}
