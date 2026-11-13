// ARE THE LENGTH FAILURES THE READINGS WHERE OUR TIPPT ROUNDS TO THE WRONG TENTH?
//
//   node dev/tippt-rounding.mjs
//
// THE SHARPEST HYPOTHESIS LEFT, and the first mechanical account of the
// residual rather than a statement that it straddles a threshold.
//
// `duplexActiveLength(pair, step, springs, tippt)` takes TIPPT as its only
// reading-specific input and immediately does
//
//     const shown = Math.round(tippt * 10) / 10;
//
// because the reference computes from the figures it displays. Its own comment
// records that using the exact value instead cost ten points - "the length sits
// on a grid and a tiny TIPPT difference flips the snap".
//
// So the whole length depends on WHICH TENTH our tippt rounds to. Our tippt
// agrees with the reference's to a median of 0.014%, which sounds decisive and
// is not the question: a reading whose true value sits near x.x5 can round the
// other way on a 0.01% difference. If the failures are concentrated where the
// two round apart, that is the mechanism - and it is the first one that would
// point at something fixable rather than at a threshold tie.
//
// `referenceIppt` is on the corpus readings imported since the pull fields were
// kept, and has never been used by anything.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const rows = [];

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;
    if (!(r.referenceIppt > 0)) continue;          // only where theirs is known

    let c;

    try { c = make(mod, r.state); } catch { continue; }

    const step = c.duplexStep;

    if (!step) continue;

    // SAME PAIR ON BOTH SIDES, or their tippt describes a different spring.
    if (`${step.outerWire}/${step.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/`
        + `${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const ours = c.duplexTipptExact;

    if (!(ours > 0)) continue;

    const ourTenth = Math.round(ours * 10);
    // Theirs is already reported at one decimal - that is the precision the
    // API returns and the precision the reference computes from.
    const theirTenth = Math.round(r.referenceIppt * 10);

    rows.push({
        rung: `${step.outerWire}/${step.innerWire}`,
        ours, theirs: r.referenceIppt,
        steps: ourTenth - theirTenth,
        relErr: ours / r.referenceIppt - 1,
        ok: c.duplexInnerLength === r.expect.duplexInnerLength
            && c.duplexOuterLength === r.expect.duplexOuterLength,
    });
}

const bad = rows.filter((x) => !x.ok);
const same = rows.filter((x) => x.steps === 0);
const diff = rows.filter((x) => x.steps !== 0);

console.log(`${rows.length} readings carrying the reference's own TIPPT, `
    + `wire matching\n`);
console.log(`our TIPPT vs theirs, relative:  median `
    + `${(rows.map((x) => Math.abs(x.relErr)).sort((a, b) => a - b)[
        Math.floor(rows.length / 2)] * 100).toFixed(4)}%\n`);

console.log("1. DO WE ROUND TO THE SAME TENTH AS THE REFERENCE?\n");
console.log(`   same tenth        ${String(same.length).padStart(5)}  `
    + `${(same.length / rows.length * 100).toFixed(1)}%`);
console.log(`   a DIFFERENT tenth ${String(diff.length).padStart(5)}  `
    + `${(diff.length / rows.length * 100).toFixed(1)}%`);

const bySteps = new Map();

for (const x of rows) bySteps.set(x.steps, (bySteps.get(x.steps) ?? 0) + 1);
console.log("   by how many tenths: "
    + [...bySteps].sort((a, b) => a[0] - b[0])
        .map(([k, v]) => `${k > 0 ? "+" : ""}${k}:${v}`).join("  "));

console.log("\n2. AND IS THAT WHERE THE LENGTH FAILURES ARE?\n");
console.log("   group                 n     failing    failure rate");

const rate = (label, set) => {
    if (!set.length) return;

    const f = set.filter((x) => !x.ok).length;

    console.log(`   ${label.padEnd(20)}${String(set.length).padStart(5)}`
        + `${String(f).padStart(10)}${(f / set.length * 100).toFixed(1).padStart(13)}%`);
};

rate("same tenth", same);
rate("different tenth", diff);
console.log("");
rate("ALL", rows);

console.log(`\n   ${bad.filter((x) => x.steps !== 0).length} of ${bad.length} `
    + `failures are on a different tenth`);

console.log("\n   A MUCH HIGHER failure rate on the different-tenth group is the");
console.log("   mechanism: the length is decided by a rounded TIPPT and we land");
console.log("   on the wrong side of the boundary. That would be the first");
console.log("   fixable account of the residual - it points at TIPPT precision,");
console.log("   not at a threshold tie.");
console.log("   SIMILAR rates mean the rounding is not what separates them and");
console.log("   the straddling account stands.");
