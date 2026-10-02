// Fold a pull into dev/corpus.json so the readings become regression-protected.
//
//   node dev/import.mjs <pulled.json> <id-prefix> "<source sentence>"
//
// WHY THIS EXISTS. corpus.json is what dev/replay.mjs asserts against, and it
// was being built by hand. dev/derive.mjs reads the pulls directly, so a pull
// could teach the model a band while never entering the regression suite - the
// model would fit it and nothing would notice if a later derive broke it. That
// is exactly what happened to hi-lift: 47 readings trained the bands and only
// one hi-lift reading was ever asserted.
//
// The filter here is deliberately the same shape as the deriver's: Duplex only,
// the calibrated pair only, both springs present, and a lift that is either
// plain standard or hi-lift with a number attached. A row that fails any of
// those is reported, not dropped quietly.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const [pullFile, prefix, sourceText] = process.argv.slice(2);

if (!pullFile || !prefix) {
    console.error("usage: node dev/import.mjs <pulled.json> <id-prefix> \"<source>\"");
    process.exit(1);
}

// The reference encodes our "LHR" (low headroom) track as radius 10 - it is a
// radius there, not a lift type, and the user confirmed the two are the same
// option on the web calculator. Verified on D525-216 at 600 lb / 8'0" /
// 2 springs: reference r10 gives multiplier 0.477011 and our LHR gives the
// same to 3.7e-07. Without this mapping every radius-10 reading arrives as
// radius "10", which the app does not offer, and is scored against the
// radius-15 baseline instead.
const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };
const ourRadius = (r) => REF_RADIUS[Number(r)] ?? String(r);

const PAIR = '3 3/4" inside 6"';
const wire = (w) => `${w}"`;
const r2 = (x) => Math.round(x * 100) / 100;
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));
const have = new Set(corpus.readings.map((r) => r.id));
const skipped = {};
const skip = (why) => { skipped[why] = (skipped[why] ?? 0) + 1; };
const added = [];

for (const r of JSON.parse(readFileSync(pullFile, "utf8"))) {
    if (r.error) {
        skip(`request error: ${r.error}`);
        continue;
    }

    const i = r.input;
    const d = r.data;

    if (!d || !d.innerSpring || !d.outerSpring) {
        skip("no spring in response");
        continue;
    }

    if ((i.assembly ?? "Duplex") !== "Duplex") {
        skip(`assembly ${i.assembly}`);
        continue;
    }

    if (Number(i.innerId) !== 3.75 || Number(i.outerId) !== 6) {
        skip(`spring ids ${i.innerId}/${i.outerId}`);
        continue;
    }

    const raw = i.lift ?? "Standard";
    const hi = raw === "HiLift" || raw === "Hi-Lift";

    if (!hi && raw !== "Standard") {
        skip(`unrecognised lift ${raw}`);
        continue;
    }

    if (hi && !(Number(i.hiLift) > 0)) {
        skip("hi-lift row without a hiLift value");
        continue;
    }

    const inner = d.innerSpring;
    const outer = d.outerSpring;
    const w = String(i.widthInches ?? 108);
    const tag = [
        prefix,
        String(outer.wireSize).replace("0.", ""),
        String(inner.wireSize).replace("0.", ""),
        `${i.weight}lb`,
        `${i.heightInches}in`,
        `${i.springs}spr`,
        hi ? `hl${i.hiLift}` : null,
        `t${i.cycles}`,
    ].filter(Boolean).join("-");

    if (have.has(tag)) {
        skip("already in corpus");
        continue;
    }

    have.add(tag);

    const state = {
        assembly: "Duplex",
        drum: i.drum,
        springId: PAIR,
        springs: i.springs,
        radius: ourRadius(i.radius),
        ...(hi ? { liftType: "Hi-Lift", liftin: String(i.hiLift) } : {}),
        cycles: Number(i.cycles).toLocaleString("en-US"),
        weight: String(i.weight),
        doorHeightFeet: Math.floor(i.heightInches / 12),
        doorHeightInches: i.heightInches % 12,
        doorWidthFeet: Math.floor(Number(w) / 12),
        doorWidthInches: Number(w) % 12,
    };

    added.push({
        id: tag,
        status: "verified",
        source: sourceText ?? `Reference calculator, automated pull ${pullFile}.`,
        state,
        expect: {
            duplexInnerWire: wire(inner.wireSize),
            duplexOuterWire: wire(outer.wireSize),
            duplexInnerLength: inner.springLength,
            duplexOuterLength: outer.springLength,
            duplexInnerWeight: r2(inner.springWeight),
            duplexOuterWeight: r2(outer.springWeight),
        },
        tolerance: { duplexInnerWeight: 0.02, duplexOuterWeight: 0.02 },
        referenceCycles: d.cycles,
    });
}

corpus.readings.push(...added);
writeFileSync(join(HERE, "corpus.json"), JSON.stringify(corpus, null, 1) + "\n");

console.log(`${added.length} reading(s) added -> corpus.json (now ${corpus.readings.length})`);

if (Object.keys(skipped).length) {
    console.log("skipped:");
    for (const [why, n] of Object.entries(skipped).sort((a, b) => b[1] - a[1])) {
        console.log(`  ${String(n).padStart(4)}  ${why}`);
    }
}
