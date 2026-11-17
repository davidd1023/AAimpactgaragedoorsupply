// THE ORACLE: HAND THE MODEL THE REFERENCE'S OWN TIPPT AND SEE WHAT IS LEFT.
//
//   node dev/tippt-oracle.mjs
//
// WHY THIS IS THE RIGHT EXPERIMENT TO RUN BEFORE ANY OTHER TIPPT IDEA.
// `duplexActiveLength` takes TIPPT as its only reading-specific input and
// rounds it to a tenth; everything else it uses is per-rung. So the whole
// chain from the door's inputs down to the length passes through ONE number.
//
// That means a single measurement bounds every possible improvement to that
// chain at once: replace our TIPPT with the reference's own reported figure -
// a perfect oracle, unobtainable in production - and score the length. What
// that recovers is the CEILING on refitting the multiplier, the weight model,
// rEff, the turns, the rounding mode, or anything else upstream.
//
// If the oracle recovers little, every one of those ideas is dead at once and
// no further work upstream of TIPPT is worth doing. That is a far stronger
// statement than testing them one at a time, and it costs no requests.
//
// IT IS NOT CIRCULAR. The reference's TIPPT is an INPUT we inject, not an
// output we score against; what is scored is the LENGTH, reported separately.
//
// IT READS THE CORPUS, not the raw pulls, because the corpus carries a
// ready-made `state` and this file has three times recorded a diagnostic that
// built its own and quietly measured nothing. 706 rows carry `referenceIppt`
// - only the batches pulled after `import.mjs` started keeping it - so the
// band mix is printed below rather than assumed to be representative.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const rows = [];

for (const r of corpus.readings) {
    if (r.referenceIppt === undefined) continue;
    if (r.expect?.duplexInnerLength === undefined) continue;

    let ours, oracle;

    try {
        ours = make(mod, r.state);
        oracle = make(mod, r.state);
    } catch {
        continue;
    }

    const step = ours.duplexStep;

    if (!step) continue;

    // Score length only where the WIRE already agrees - otherwise the two
    // lengths describe different springs. Same rule as envelope.mjs, and the
    // wire is read off `duplexStep`, which is where it actually lives.
    const wireOk = `${step.outerWire}/${step.innerWire}`
        === `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;

    if (!wireOk) continue;

    const hit = (c) => c.duplexInnerLength === r.expect.duplexInnerLength
        && c.duplexOuterLength === r.expect.duplexOuterLength;

    // The getter is on the prototype, so an own property shadows it and every
    // downstream getter follows.
    Object.defineProperty(oracle, "duplexTipptExact", {
        value: r.referenceIppt,
        configurable: true,
    });

    const longest = Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength);

    rows.push({
        before: hit(ours),
        after: hit(oracle),
        band: longest > 120 ? "over 120" : longest > 96 ? "96-120" : "under 96",
        ourT: ours.duplexTipptExact,
        refT: r.referenceIppt,
    });
}

const n = rows.length;

if (!n) {
    console.error("no scorable rows - check that corpus.json carries referenceIppt");
    process.exit(1);
}

const before = rows.filter((r) => r.before).length;
const after = rows.filter((r) => r.after).length;
const pct = (a) => `${(100 * a / n).toFixed(2)}%`;

console.log("=".repeat(72));
console.log(`THE TIPPT ORACLE - ${n} duplex readings where our wire already agrees`);
console.log("=".repeat(72));
console.log(`  as shipped                 ${String(before).padStart(6)}  ${pct(before)}`);
console.log(`  with the REFERENCE's tippt ${String(after).padStart(6)}  ${pct(after)}`);
console.log(`  ${"-".repeat(46)}`);
console.log(`  THE CEILING on every idea upstream of tippt: `
    + `${after - before >= 0 ? "+" : ""}${after - before} readings `
    + `(${(100 * (after - before) / n).toFixed(2)} points)`);

const fixed = rows.filter((r) => !r.before && r.after).length;
const broken = rows.filter((r) => r.before && !r.after).length;

console.log(`\n  fixed by a perfect tippt: ${fixed}     BROKEN by it: ${broken}`);
console.log("  (anything broken means the rung table has absorbed part of our"
    + "\n   own tippt's bias - the same way `b` absorbs a stiffness scale)");

console.log("\n  by band:");
for (const b of ["under 96", "96-120", "over 120"]) {
    const v = rows.filter((r) => r.band === b);

    if (!v.length) continue;

    const bb = v.filter((r) => r.before).length, aa = v.filter((r) => r.after).length;

    console.log(`    ${b.padEnd(10)}${String(v.length).padStart(5)}`
        + `   shipped ${(100 * bb / v.length).toFixed(1).padStart(5)}%`
        + `   oracle ${(100 * aa / v.length).toFixed(1).padStart(5)}%`
        + `   ${aa - bb >= 0 ? "+" : ""}${aa - bb}`);
}

// HOW OFTEN THE ROUNDED TENTH EVEN DIFFERS. If it rarely does, the oracle
// cannot help however accurate it is, and that is the whole explanation.
const diff = rows.filter((r) =>
    Math.round(r.ourT * 10) !== Math.round(r.refT * 10)).length;

console.log(`\n  our tippt rounds to a DIFFERENT tenth than theirs on `
    + `${diff} of ${n} (${(100 * diff / n).toFixed(2)}%)`);
console.log("  That rate is the hard ceiling: where the tenth already agrees,"
    + "\n  a better tippt cannot change a single length.");
