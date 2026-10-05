// The Duplex regression suite.
//
//   node dev/replay.mjs                  run everything
//   node dev/replay.mjs --update-golden  re-record the Single snapshot
//   node dev/replay.mjs --only=single    one section (single|invariants|corpus)
//
// THREE SECTIONS, in order of how much they are trusted:
//
//   SINGLE GOLDEN   A snapshot of the Single assembly's outputs. Single is
//                   known good and is NOT being worked on, so this exists
//                   purely to prove that Duplex changes do not touch it. A
//                   diff here means stop.
//
//   INVARIANTS      Laws that hold without reference data (see invariants.mjs).
//
//   CORPUS          Readings taken off the manufacturer's reference calculator.
//                   The only check that can confirm ACCURACY rather than
//                   self-consistency.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { load, make } from "./harness.mjs";
import { singleCases, SINGLE_OUTPUTS } from "./cases.mjs";
import { INVARIANTS } from "./invariants.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const GOLDEN = join(HERE, "golden-single.json");
const CORPUS = join(HERE, "corpus.json");

const args = process.argv.slice(2);
const only = (args.find((a) => a.startsWith("--only=")) || "").split("=")[1];
const updating = args.includes("--update-golden");

// Floats are pinned to 10 decimals so the snapshot is stable across platforms
// without hiding a real change: every displayed value is rounded far shorter.
function freeze(value) {
    if (typeof value === "number") {
        return Number.isFinite(value) ? Number(value.toFixed(10)) : String(value);
    }

    if (Array.isArray(value)) {
        return value.map(freeze);
    }

    if (value && typeof value === "object") {
        return Object.fromEntries(
            Object.keys(value).sort().map((k) => [k, freeze(value[k])])
        );
    }

    return value;
}

function snapshotSingle(mod) {
    const rows = [];

    for (const state of singleCases()) {
        const component = make(mod, state);
        const out = {};

        for (const key of SINGLE_OUTPUTS) {
            try {
                out[key] = freeze(component[key]);
            } catch (error) {
                out[key] = `THREW: ${error.message}`;
            }
        }

        rows.push({ state: freeze(state), out });
    }

    return rows;
}

function runSingle(mod) {
    const current = snapshotSingle(mod);

    if (updating || !existsSync(GOLDEN)) {
        writeFileSync(GOLDEN, JSON.stringify(current, null, 1) + "\n");
        console.log(`  recorded ${current.length} Single cases -> dev/golden-single.json`);

        return 0;
    }

    const saved = JSON.parse(readFileSync(GOLDEN, "utf8"));
    let diffs = 0;

    if (saved.length !== current.length) {
        console.log(`  GRID CHANGED: golden has ${saved.length} cases, now ${current.length}.`);
        console.log("  Re-record with --update-golden only if you MEANT to change the grid.");

        return 1;
    }

    for (let i = 0; i < saved.length; i++) {
        for (const key of SINGLE_OUTPUTS) {
            const a = JSON.stringify(saved[i].out[key]);
            const b = JSON.stringify(current[i].out[key]);

            if (a !== b) {
                diffs++;

                if (diffs <= 20) {
                    console.log(`  ${key}: ${a} -> ${b}`);
                    console.log(`    case ${JSON.stringify(saved[i].state)}`);
                }
            }
        }
    }

    if (diffs) {
        console.log(`\n  *** ${diffs} SINGLE-PATH OUTPUT(S) MOVED. Single is not being`);
        console.log("  *** worked on, so this is a regression. Fix before going further.");
    } else {
        console.log(`  ${current.length} Single cases byte-identical to the snapshot.`);
    }

    return diffs ? 1 : 0;
}

function runInvariants(mod) {
    let bad = 0;

    for (const { name, run } of INVARIANTS) {
        const fails = run(mod);

        if (!fails.length) {
            console.log(`  PASS  ${name}`);
            continue;
        }

        bad++;
        console.log(`  FAIL  ${name}  (${fails.length} violation(s))`);

        for (const line of fails.slice(0, 4)) {
            console.log(`          ${line}`);
        }

        if (fails.length > 4) {
            console.log(`          ... and ${fails.length - 4} more`);
        }
    }

    return bad;
}

function runCorpus(mod) {
    if (!existsSync(CORPUS)) {
        console.log("  no corpus.json yet - see dev/README.md");

        return 0;
    }

    const { readings } = JSON.parse(readFileSync(CORPUS, "utf8"));
    const usable = readings.filter((r) => r.status === "verified");
    const byStatus = {};

    for (const r of readings) {
        byStatus[r.status] = (byStatus[r.status] || 0) + 1;
    }

    let failedReadings = 0;
    let outOfRange = 0;

    // WHAT THE MODEL CLAIMS, AND NOTHING MORE. The reference will not build a
    // spring outside 0-120" - it answers "Only spring lengths between 0 and
    // 120\" are supported" and then prints a number anyway, which in this
    // corpus runs to 2,177". dev/derive.mjs has always refused to FIT those
    // readings, for the good reason that they are the furthest from any grid
    // and outvote the real ones. Asserting them here anyway left 28 readings
    // that could never pass, so the suite reported a failing section
    // permanently - and a suite that is always red hides the regression it
    // exists to catch.
    //
    // The WIRE is still asserted on these: picking the pairing is a separate
    // claim from quoting its length, the reference's own choice is meaningful
    // whatever length comes out, and those readings stay in the fit for
    // exactly that reason. Only the length and the weight derived from it are
    // let go.
    const LENGTH_FIELDS = /Length$|Weight$/;
    const buildable = (r) => {
        const l = r.expect?.duplexInnerLength;

        return l === undefined || (l > 0 && l <= 120);
    };

    for (const reading of usable) {
        const component = make(mod, reading.state);
        const inRange = buildable(reading);
        let ok = true;

        if (!inRange) {
            outOfRange++;
        }

        for (const [key, want] of Object.entries(reading.expect)) {
            if (!inRange && LENGTH_FIELDS.test(key)) {
                continue;
            }

            const got = component[key];
            const matches =
                typeof want === "number"
                    ? Math.abs(got - want) <= (reading.tolerance?.[key] ?? 0)
                    : String(got) === String(want);

            if (!matches) {
                ok = false;
                console.log(`  FAIL  ${reading.id}  ${key}: want ${want}, got ${got}`);
            }
        }

        if (!ok) {
            failedReadings++;
        }
    }

    const extra = Object.entries(byStatus)
        .filter(([status]) => status !== "verified")
        .map(([status, n]) => `${n} ${status}`)
        .join(", ");

    console.log(
        `  ${usable.length - failedReadings}/${usable.length} verified reading(s) reproduced` +
        (extra ? `  (plus ${extra} - not asserted)` : "")
    );

    if (outOfRange) {
        console.log(
            `  ${outOfRange} of those are past the reference's own 120" limit, ` +
            "so their length and weight are not asserted - only the wire"
        );
    }

    return failedReadings ? 1 : 0;
}

const mod = await load();
let failed = 0;

if (!only || only === "single") {
    console.log("\nSINGLE GOLDEN (must not move)");
    failed += runSingle(mod);
}

if (!only || only === "invariants") {
    console.log("\nDUPLEX INVARIANTS (no reference data needed)");
    failed += runInvariants(mod);
}

if (!only || only === "corpus") {
    console.log("\nREFERENCE CORPUS (accuracy)");
    failed += runCorpus(mod);
}

console.log(failed ? `\n${failed} section(s) failing.\n` : "\nAll sections clean.\n");
process.exit(failed ? 1 : 0);
