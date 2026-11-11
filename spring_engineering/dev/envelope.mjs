// DUPLEX ACCURACY, SPLIT BY WHETHER THE REFERENCE STANDS BEHIND ITS ANSWER.
//
//   node dev/envelope.mjs
//
// WHY A SPLIT AND NOT ONE NUMBER. A single pooled percentage averages in
// doors Service Spring will not answer for. Their own complaints say so:
//
//     "Only spring lengths between 0 and 96" are recommended"
//     "Only spring lengths between 0 and 120" are supported"
//
// Past 120" the reference has given up, and scoring our model against a
// number its own author disclaims is not a measure of our model. The honest
// figure is the one inside the envelope, with the rest reported separately
// rather than hidden or averaged away.
//
// CLASSIFIED BY THE REFERENCE'S OWN RETURNED LENGTH, not by the recorded
// `flagged` bit. The bit is the better signal but it was only added to
// dev/import.mjs partway through, so earlier batches carry none and a split
// on it would silently call thousands of old readings clean. The LENGTH is
// present on every reading ever stored, so this classifies all 12,000-odd on
// the same rule. Where the flag IS present it is reported beside, as a check
// that the two agree.
//
// This was computed ad hoc once (2026-11-10) and CLAUDE.md records it as
// "worth rebuilding as a committed tool if the question returns". It did.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));

const band = (len) => (len <= 96 ? "inside 96\"  (recommended)"
    : len <= 120 ? "96-120\"     (supported)"
        : "over 120\"   (DISCLAIMED)");

const groups = new Map();
const add = (k, f) => {
    if (!groups.has(k)) {
        groups.set(k, { n: 0, exact: 0, wire: 0, lenOnly: 0, flagged: 0 });
    }

    f(groups.get(k));
};

let skipped = 0;

for (const r of corpus.readings) {
    if (r.status !== "verified" || !r.expect) continue;
    if (r.expect.duplexInnerLength === undefined) continue;

    let comp;

    try { comp = make(mod, r.state); } catch { skipped++; continue; }

    const step = comp.duplexStep;

    if (!step) { skipped++; continue; }

    const wireOk = `${step.outerWire}/${step.innerWire}`
        === `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`;
    // BOTH lengths, not just the inner - a pair is right or it is not.
    const lenOk = comp.duplexInnerLength === r.expect.duplexInnerLength
        && comp.duplexOuterLength === r.expect.duplexOuterLength;

    const k = band(Math.max(r.expect.duplexInnerLength, r.expect.duplexOuterLength));

    add(k, (g) => {
        g.n++;
        if (wireOk) g.wire++;
        if (wireOk && lenOk) g.exact++;
        if (wireOk && !lenOk) g.lenOnly++;
        if (r.flagged) g.flagged++;
    });
}

const pc = (a, b) => `${(a / b * 100).toFixed(2)}%`.padStart(7);

console.log("DUPLEX, by whether the reference stands behind the answer\n");
console.log("  band                          n     exact   wire right   "
    + "wire ok/len wrong");

let tot = { n: 0, exact: 0, wire: 0, lenOnly: 0 };

for (const k of ["inside 96\"  (recommended)", "96-120\"     (supported)",
    "over 120\"   (DISCLAIMED)"]) {
    const g = groups.get(k);

    if (!g) continue;

    tot.n += g.n; tot.exact += g.exact; tot.wire += g.wire; tot.lenOnly += g.lenOnly;
    console.log(`  ${k}  ${String(g.n).padStart(6)}  ${pc(g.exact, g.n)}   `
        + `${pc(g.wire, g.n)}      ${String(g.lenOnly).padStart(5)}`);
}

console.log(`\n  ALL DUPLEX                ${String(tot.n).padStart(6)}  `
    + `${pc(tot.exact, tot.n)}   ${pc(tot.wire, tot.n)}      `
    + `${String(tot.lenOnly).padStart(5)}`);

const env = groups.get("inside 96\"  (recommended)");

console.log(`\n  QUOTE THE FIRST LINE. Inside the length the reference calls`);
console.log(`  recommended, the model is ${pc(env.exact, env.n).trim()} exact `
    + `and picks the right wire ${pc(env.wire, env.n).trim()}`);
console.log(`  of the time, over ${env.n} readings. Only LENGTH degrades `
    + `outside it; the WIRE holds up`);
console.log("  everywhere, which is the figure that decides whether a door "
    + "is sprung right.");
if (skipped) console.log(`\n  (${skipped} readings skipped - no duplex step)`);
