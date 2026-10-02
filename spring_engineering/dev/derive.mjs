// Derive the Duplex calibration table from every reading available.
//
//   node dev/derive.mjs            print the table
//   node dev/derive.mjs --json     machine-readable
//
// WHY. The calibration table used to be hand-maintained, which is how it
// drifted from its own comments in the first place. Every number in it is a
// function of the readings, so it should be COMPUTED from them:
//
//   rungs       every outer/inner pairing the reference has been seen to use
//   K           the cycle model run backwards on each reading, median per rung
//   tLo / tHi   the length thresholds, where readings bracket them
//
// It reads dev/corpus.json plus any dev/pulled*.json, so a new pull improves
// the table by re-running this rather than by editing JavaScript.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TC = 10.2;
const COEFF = 124205;
const WEXP = 2.79;
const CEXP = 4.67;
const PAIR = '3 3/4" inside 6"';

const divider = (wire, id) =>
    (30000000 * Math.pow(wire, 5)) / (TC * (id + wire));

const mod = await load();

// --- gather every reading, from pulls and from the hand-entered corpus ------
const readings = [];

// Ingestion is STRICT and it reports what it drops. Every field the model
// depends on has to be present and unambiguous, because the failure mode here
// is silent: a row that is quietly mislabelled still produces a band, and that
// band is indistinguishable from a real one afterwards. Four real hazards sat
// in the pull directory:
//
//   - pulled-hl3/hl4 hold Single rows, and this loop used to hardcode
//     assembly "Duplex" - so a Single answer would have taught a Duplex band.
//   - pulled-hl.json spells the lift "Hi-Lift"; pulled-hl5 spells it
//     "HiLift". Matching one spelling reads the other as standard lift.
//   - pulled-hl/hl2/hl3/hl4 predate the confirmed hiLift parameter name. The
//     server ignored the guessed names, so those rows are STANDARD-lift
//     answers wearing a hi-lift label. They are the most dangerous of the
//     four and they are why a hi-lift row must carry a numeric hiLift.
//   - one row has innerSpring null, another has no spring ids at all.
//
// So: Duplex only, the calibrated pair only, both springs present, and a lift
// that is either exactly standard or hi-lift with a number attached.
const skipped = {};
const skip = (why) => { skipped[why] = (skipped[why] ?? 0) + 1; };

for (const f of readdirSync(HERE).filter((f) => /^pulled.*\.json$/.test(f))) {
    for (const r of JSON.parse(readFileSync(join(HERE, f), "utf8"))) {
        if (r.error) {
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

        // The lift has to be one of exactly two recognised shapes.
        const raw = i.lift ?? "Standard";
        const hi = raw === "HiLift";

        if (!hi && raw !== "Standard") {
            skip(`unrecognised lift ${raw}`);
            continue;
        }

        if (hi && !(Number(i.hiLift) > 0)) {
            skip("hi-lift row without a hiLift value (pre-fix guess)");
            continue;
        }

        readings.push({
            state: {
                assembly: "Duplex", drum: i.drum, springId: PAIR,
                springs: i.springs, radius: String(i.radius),
                liftType: hi ? "Hi-Lift" : "Standard",
                liftin: hi ? String(i.hiLift) : "",
                cycles: Number(i.cycles).toLocaleString("en-US"),
                weight: String(i.weight),
                doorWidthFeet: Math.floor((i.widthInches ?? 108) / 12),
                doorWidthInches: (i.widthInches ?? 108) % 12,
                doorHeightFeet: Math.floor(i.heightInches / 12),
                doorHeightInches: i.heightInches % 12,
            },
            hiLift: hi ? Number(i.hiLift) : 0,
            outer: d.outerSpring.wireSize,
            inner: d.innerSpring.wireSize,
            length: d.innerSpring.springLength,
            cycles: d.cycles,
        });
    }
}

// stderr, not stdout: --json mode pipes stdout straight into apply.sh, so a
// human-readable line there is a parse error.
if (Object.keys(skipped).length) {
    console.error("skipped rows (not silently - each would have taught a false band):");
    for (const [why, n] of Object.entries(skipped).sort((a, b) => b[1] - a[1])) {
        console.error(`  ${String(n).padStart(4)}  ${why}`);
    }
    console.error("");
}

for (const r of JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8")).readings) {
    if (!r.expect || r.expect.duplexInnerLength === undefined) {
        continue;
    }

    if (r.status === "partial" || r.status === "superseded") {
        continue;
    }

    if ((r.state.springId || "").indexOf("3 3/4") !== 0) {
        continue;
    }

    readings.push({
        state: r.state,
        // Same hiLift marker the pull path sets. Without it the hi-lift
        // holdout below silently withholds nothing from this half of the
        // data, and reports a perfect out-of-sample score that is really
        // in-sample. That mistake was made once already.
        hiLift: r.state.liftType === "Hi-Lift" ? Number(r.state.liftin) || 0 : 0,
        outer: parseFloat(r.expect.duplexOuterWire),
        inner: parseFloat(r.expect.duplexInnerWire),
        length: r.expect.duplexInnerLength,
        cycles: r.referenceCycles,
    });
}

// --- per rung: K from the cycle counts, thresholds from the lengths ---------
const rungs = new Map();

for (const r of readings) {
    const c = make(mod, r.state);
    const springs = Number(r.state.springs) || 2;

    if (!c.tipptExact || !c.turnsExact) {
        continue;
    }

    const key = r.outer + "/" + r.inner;

    if (!rungs.has(key)) {
        rungs.set(key, { outer: r.outer, inner: r.inner, Ks: [], lens: [] });
    }

    const g = rungs.get(key);

    if (r.cycles > 0) {
        const torque = (COEFF * Math.pow(r.inner, WEXP)) / Math.pow(r.cycles, 1 / CEXP);
        const body = divider(r.inner, 3.75) * c.turnsExact / torque;

        g.Ks.push(body * c.tipptExact / (springs / 2));
    }

    const active =
        springs * (divider(r.inner, 3.75) + divider(r.outer, 6)) / c.tipptExact;
    const whole = Math.floor(active);

    g.lens.push({
        springs, active, frac: active - whole,
        bonus: Number((r.length - whole).toFixed(2)),
    });
}

// K FROM THE REFERENCE'S OWN SWITCH POINTS, which is far tighter than
// inverting a cycle count.
//
// At the heaviest door still using a rung, that rung must clear
// DUPLEX_ACCEPT_FRACTION x target; at the next door up it must not. Since
// cycles rise monotonically with K, each side gives a bound, and a pair of
// readings a couple of pounds apart pins K to about 0.15% - against roughly 1%
// from a cycle count, which the reference rounds to the nearest thousand.
//
// This is the same lever as the original 726/727 lb accept/reject pair: a
// boundary is worth far more than a reading away from one.
function boundsFromSwitches(readings) {
    const F = mod.DUPLEX_ACCEPT_FRACTION;
    const cfg = new Map();

    for (const r of readings) {
        const st = r.state;
        const key = [st.drum, st.springs, st.radius, st.doorHeightFeet,
                     st.doorHeightInches, st.cycles].join("|");

        if (!cfg.has(key)) {
            cfg.set(key, []);
        }

        cfg.get(key).push(r);
    }

    const out = new Map();

    for (const rows of cfg.values()) {
        rows.sort((a, b) => Number(a.state.weight) - Number(b.state.weight));

        for (let n = 1; n < rows.length; n++) {
            const a = rows[n - 1];
            const b = rows[n];
            const ka = a.outer + "/" + a.inner;

            if (ka === b.outer + "/" + b.inner) {
                continue;
            }

            if (Number(b.state.weight) - Number(a.state.weight) > 6) {
                continue;
            }

            const target = Number(String(a.state.cycles).replace(/,/g, "")) * F;
            const torque = (COEFF * Math.pow(a.inner, WEXP)) / Math.pow(target, 1 / CEXP);
            const springs = Number(a.state.springs) || 2;

            if (!out.has(ka)) {
                out.set(ka, { lo: [], hi: [] });
            }

            for (const [side, reading] of [["lo", a], ["hi", b]]) {
                const c = make(mod, reading.state);

                if (!c.tipptExact || !c.turnsExact) {
                    continue;
                }

                out.get(ka)[side].push(
                    divider(a.inner, 3.75) * c.turnsExact * c.tipptExact /
                    (torque * (springs / 2))
                );
            }
        }
    }

    return out;
}

// HOLDOUT. With HOLDOUT_MOD=n every nth reading is withheld from the fit, so
// the model can be scored on readings it never saw. Without it nothing is
// held back and the fit uses everything.
const HOLDOUT_MOD = Number(process.env.HOLDOUT_MOD || 0);

if (HOLDOUT_MOD > 1) {
    const kept = readings.filter((_, i) => i % HOLDOUT_MOD !== 0);

    readings.length = 0;
    readings.push(...kept);
}

// DEDUPLICATE. This reads both dev/pulled*.json and dev/corpus.json, and
// dev/import.mjs folds pulls INTO the corpus - so from the moment the import
// workflow started, almost every reading has been ingested twice, once as a
// pull row and once as a corpus row.
//
// Uniform double-counting cancels, which is why this hid for eight batches.
// It stopped cancelling the moment one group was weighted differently from
// the rest: hi-lift lived only in the pulls (1x) while standard lift was in
// both (2x), so hi-lift lost every tie. Importing the hi-lift readings made
// them 2x as well, they started winning those ties instead, and 38 standard
// -lift readings broke. The band fitter was never at fault - the input was
// silently weighted.
//
// So: collapse exact duplicates, and if the same inputs ever carry DIFFERENT
// outputs, say so loudly instead of letting the fitter average two readings
// that cannot both be true.
const seenKey = new Map();
const collisions = [];
const unique = [];

for (const r of readings) {
    const st = r.state;
    const key = [
        st.drum, st.springs, st.radius, st.liftType ?? "Standard", st.liftin ?? "",
        st.cycles, st.weight, st.doorHeightFeet, st.doorHeightInches,
    ].join("|");
    const out = `${r.outer}/${r.inner}/${r.length}`;
    const prev = seenKey.get(key);

    if (prev === undefined) {
        seenKey.set(key, out);
        unique.push(r);
    } else if (prev !== out) {
        collisions.push(`  ${key}  ->  ${prev}  vs  ${out}`);
    }
}

console.error(`deduplicated: ${readings.length} ingested -> ${unique.length} distinct`);

if (collisions.length) {
    console.error(`SAME INPUTS, DIFFERENT OUTPUTS (${collisions.length}) - these cannot both be right:`);
    console.error(collisions.slice(0, 20).join("\n"));
}

console.error("");
readings.length = 0;
readings.push(...unique);

// HI-LIFT HOLDOUT. Runs AFTER the dedup above, and must: a reading arrives
// twice (once from its pull, once from the corpus), so withholding by
// ingestion index before dedup would withhold one copy and leave the other
// in the fit - scoring the model on data it still trained on. Hi-lift is ~48 of ~3900 readings, so the global holdout
// above barely touches it and an in-sample hi-lift score means nothing. With
// HL_HOLDOUT_MOD=n and HL_HOLDOUT_REM=k, every hi-lift reading whose hi-lift
// index is k mod n is withheld - standard lift untouched. Rotating k over
// 0..n-1 scores every hi-lift reading exactly once, out of sample.
const HL_MOD = Number(process.env.HL_HOLDOUT_MOD || 0);
const HL_REM = Number(process.env.HL_HOLDOUT_REM || 0);

if (HL_MOD >= 1) {
    let seen = -1;
    const withheld = [];
    const kept = readings.filter((r) => {
        if (!r.hiLift) {
            return true;
        }

        seen += 1;

        if (seen % HL_MOD !== HL_REM) {
            return true;
        }

        withheld.push(`${r.state.weight}|${r.state.doorHeightFeet}|${r.hiLift}|${r.state.springs}|${r.state.cycles}`);

        return false;
    });

    console.error(`hi-lift holdout: withheld ${withheld.length} of ${seen + 1}`);
    console.error(withheld.map((w) => `  ${w}`).join("\n") + "\n");
    readings.length = 0;
    readings.push(...kept);
}

const switchBounds = boundsFromSwitches(readings);

const median = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);

    return s[Math.floor(s.length / 2)];
};

const contradictions = [];
const overfit = [];
const MAX_BANDS = Number(process.env.MAX_BANDS || 64);


// For each rung AND spring count, derive the bonus as a piecewise-constant
// function of frac(active).
//
// This replaces a single threshold pair per rung. It has to: 1 spring, 2, 3 and
// 4 sit on different quarter-inch grids and take different bonus values, so one
// rule per rung cannot describe them. Bands are emitted ONLY where readings
// cover them, and a rung/count with no readings falls back to plain rounding.
function bands(ls) {
    const pts = ls.slice().sort((x, y) => x.frac - y.frac);
    const groups = [];

    for (const p of pts) {
        const last = groups[groups.length - 1];

        if (last && last.bonus === p.bonus) {
            last.hi = p.frac;
        } else {
            groups.push({ lo: p.frac, hi: p.frac, bonus: p.bonus });
        }
    }

    if (groups.length === 1) {
        return { bands: [{ upTo: 1, bonus: groups[0].bonus }], clean: true };
    }

    // a band boundary sits midway between the last frac of one group and the
    // first of the next; non-monotonic data shows up as groups that interleave
    const out = [];
    let clean = true;

    for (let i = 0; i < groups.length; i++) {
        if (i === groups.length - 1) {
            out.push({ upTo: 1, bonus: groups[i].bonus });
            break;
        }

        const edge = (groups[i].hi + groups[i + 1].lo) / 2;

        if (out.length && edge <= out[out.length - 1].upTo) {
            clean = false;
            continue;
        }

        out.push({ upTo: Number(edge.toFixed(3)), bonus: groups[i].bonus });
    }

    return { bands: out, clean };
}

// Prefer the switch-point window where there is one - it is about seven times
// tighter than the cycle-count estimate. Where the window and the cycle
// estimate agree, keep the estimate; where they do not, the window wins,
// because a rounded cycle count is the weaker evidence.
function pickK(g) {
    const fromCycles = g.Ks.length ? Number(median(g.Ks).toFixed(1)) : null;
    const b = switchBounds.get(g.outer + "/" + g.inner);

    if (!b || !b.lo.length || !b.hi.length) {
        return fromCycles;
    }

    const lo = Math.max(...b.lo);
    const hi = Math.min(...b.hi);

    if (!(hi > lo)) {
        return fromCycles;
    }

    if (fromCycles !== null && fromCycles >= lo && fromCycles <= hi) {
        return fromCycles;
    }

    return Number(((lo + hi) / 2).toFixed(1));
}

const out = [...rungs.values()]
    .map((g) => {
        const S = 2 * (divider(g.inner, 3.75) + divider(g.outer, 6));
        const byCount = {};

        for (const sp of [1, 2, 3, 4]) {
            const ls = g.lens.filter((l) => l.springs === sp);

            if (!ls.length) {
                continue;
            }

            const b = bands(ls);

            // only worth storing where it differs from plain round()
            const needed = ls.some(
                (l) => Math.round(l.active) !== Math.floor(l.active) + l.bonus
            );

            // REFUSE TO OVERFIT. If the bonus needs more than a few bands to
            // follow the fraction, it is not a function of the fraction: it
            // depends on the active length as well, the way the softest rung
            // does. The fitter would otherwise slice frac into alternating
            // slivers - 0.375/0.295 at one spring wanted EIGHTEEN bands
            // flipping between 0 and 1 across frac 0.67 to 1.00, which fits
            // the readings and predicts nothing.
            //
            // Past the cap the rung falls back to plain rounding and is named
            // below, which is a worse answer honestly labelled rather than a
            // better-looking one that will not hold.
            if (needed && b.bands.length <= MAX_BANDS) {
                byCount[sp] = { bands: b.bands, n: ls.length };
            } else if (needed) {
                overfit.push(
                    `${g.outer}/${g.inner} at ${sp} spring(s): ${b.bands.length} bands ` +
                    `needed over ${ls.length} readings - not a function of frac alone`
                );
            }

            if (!b.clean) {
                contradictions.push(
                    `${g.outer}/${g.inner} at ${sp} spring(s): bonus is not monotonic in frac`
                );
            }
        }

        return {
            outer: g.outer, inner: g.inner, S,
            K: pickK(g),
            n: g.Ks.length, nLen: g.lens.length, byCount,
        };
    })
    .sort((a, b) => a.S - b.S);

if (process.argv.includes("--json")) {
    console.log(JSON.stringify(out, null, 1));
} else {
    console.log(`${readings.length} readings -> ${out.length} rungs\n`);
    console.log("  outer    inner      S        K       K/S     n  nLen  bands per spring count");

    for (const r of out) {
        const bc = Object.entries(r.byCount)
            .map(([sp, v]) => `${sp}spr:${v.bands.length}b/n${v.n}`)
            .join(" ");

        console.log(
            "  " + String(r.outer).padEnd(8) + String(r.inner).padEnd(9) +
            r.S.toFixed(0).padStart(6) + String(r.K ?? "-").padStart(10) +
            (r.K ? (r.K / r.S).toFixed(4) : "     -").padStart(9) +
            String(r.n).padStart(4) + String(r.nLen).padStart(5) + "  " + bc
        );
    }

    console.log("\n  n     = readings whose cycle count fed K");
    console.log("  nLen  = readings whose length fed the thresholds");
    console.log("  Nb/nM = N bands derived from M readings; blank = plain round() is already right");

    if (overfit.length) {
        console.log("\n  RUNGS WHERE THE FRACTION ALONE DOES NOT DETERMINE THE LENGTH");
        console.log("  (left on plain rounding rather than fitted to slivers):");

        for (const o of overfit) {
            console.log("    " + o);
        }
    }

    if (contradictions.length) {
        console.log("\n  RUNGS WHERE ONE THRESHOLD CANNOT FIT THE READINGS:");

        for (const c of contradictions) {
            console.log("    " + c);
        }
    }
}
