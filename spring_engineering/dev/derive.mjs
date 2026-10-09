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

// EVALUATION PULLS ARE NOT TRAINING DATA.
//
// This reads every pulled*.json, and that silently swallowed the random
// sample: dev/pulled-rand.json is drawn uniformly from the allowed box to
// SCORE the model, and because the pull writes it incrementally, every
// apply.sh folded more of it into the fit. The score then climbed from 57.5%
// to 91.9% while I attributed the gain to a fitter change - the model was
// being measured on rows it had just been trained on.
//
// A file whose name says eval or rand is an evaluation set and is skipped
// here. Nothing stops it being imported later ON PURPOSE with
// dev/import.mjs; what must not happen is it arriving by accident.
// EVAL files score the model. BIASED files are real reference data whose
// SAMPLING makes them unfit to fit on, which is a distinction worth keeping in
// the filename.
//
// dev/biased-soft-weightonly.json is 430 readings on 0.2625/0.2253, the
// highest-traffic rung, pulled deliberately to densify it. It made that rung
// WORSE on an external sample - 58.3% to 29.2% - because of how it was swept:
// weight varied finely at FIXED height and FIXED cycle target. Active length
// is springs*(dividers)/TIPPT and TIPPT is multiplier*weight, so at fixed
// height the active length is just 1/weight. Every one of those 430 readings
// lies on a single one-dimensional curve through the (floor, fraction) plane,
// and the threshold being fitted is a surface over that plane. The fitter got
// 430 readings and almost no new information, then followed the curve off into
// territory the curve never visited.
//
// Dense is not diverse. The same flaw is why the five-fold holdout read 98%:
// the corpus is full of one-pound sweeps, so a withheld reading always has a
// neighbour one pound away.
const EVAL = /(^|-)(eval|rand|biased)/;

for (const f of readdirSync(HERE)
    .filter((f) => /^pulled.*\.json$/.test(f) && !EVAL.test(f))) {
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

        // WHETHER THE REFERENCE COMPLAINED, same rule as dev/import.mjs.
        //
        // This path did not set it, and only the corpus path did - so a flag
        // reached the fit only after a pull had been imported. A freshly
        // pulled batch read straight off disk had every flagged reading's
        // LENGTH fitted, which is the exact mistake that cost 2.7 points when
        // batch L1's flagged half was included, and about half of a uniform
        // draw is flagged.
        //
        // It was harmless while it lasted, because a pull that has been
        // imported loses the dedup to its own corpus entry, which does carry
        // the flag. It stops being harmless the moment a batch is pulled and
        // derived before it is imported - which is every batch of a pull
        // campaign.
        const flagged = (r.messages ?? [])
            .filter((m) => !/contact us/i.test(String(m))).length > 0
            || r.status !== "success";

        readings.push({
            fromCorpus: false,
            flagged,
            state: {
                assembly: "Duplex", drum: i.drum, springId: PAIR,
                springs: i.springs, radius: ourRadius(i.radius),
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

    // DELIBERATELY NOT FITTED, but still a real reading and still asserted by
    // dev/replay.mjs. Batch R1 is the case: 380 readings chosen to land within
    // 0.03 of a fitted threshold, to place those thresholds more precisely.
    //
    // It backfired. Concentrating that much data at the boundaries
    // over-weights them, and the thresholds move to fit the boundary readings
    // at the expense of ordinary doors. On the samples it had been tuned
    // against it looked like a gain; on a fresh uniform draw, dropping it from
    // the fit is worth a point of length accuracy and a wire miss:
    //
    //                      with R1 fitted   without
    //   clean wire             99.4%         100%
    //   clean length           90.3%         91.4%
    //   clean within 1"        97.7%         98.3%
    //
    // Same lesson as the 1 lb bracket batch, one level subtler: dense is not
    // diverse, and data chosen BY where the model's boundaries already sit is
    // the densest kind there is.
    //
    // ONLY THE CORPUS PATH CHECKS THIS. A pull file is read straight off disk
    // with no corpus entry to consult, so dev/pulled-R1.json must stay out of
    // dev/ or it would be fitted again. That is safe by default - pulls are
    // gitignored and do not survive a rebuild, so the corpus is what a fresh
    // build sees - but it is a real edge if the file is ever put back.
    // INGESTED, THEN EXCLUDED - not skipped here.
    //
    // Skipping at ingestion looked equivalent and was not: a reading that never
    // enters `readings` cannot take part in the dedup, so it cannot block the
    // copy of itself sitting in a pull file, and the pull copy - which carries
    // no flag - gets fitted. Putting dev/pulled-U5..U8.json back raised the
    // distinct count by exactly the 1522 readings meant to be held out.
    //
    // So they are ingested, win the dedup as corpus readings always do, and
    // are dropped where the fit is actually built. The flag now holds whether
    // the pull file is on disk or not, which is the point of it.
    const noFit = r.fit === false;

    // BOUNDARY-DENSE READINGS ARE FOR THE THRESHOLDS, NOT FOR THE STIFFNESS.
    //
    // A batch sampled deliberately NEXT to a fitted threshold is the right data
    // for placing that threshold and the wrong data for fitting the rung's
    // sMult, which every spring count of the rung shares. fitStiffness scores a
    // COUNT of readings whose snapped length comes out right, and a reading
    // sitting on a boundary is exactly the ambiguous kind - so a few hundred of
    // them outvote the ordinary doors and drag the multiplier.
    //
    // Measured: adding 353 such readings moved sMult on their three rungs by up
    // to 0.0073, which on a 30" active length is 0.22" - a fifth of an inch of
    // fraction, applied to every door on the rung including spring counts the
    // batch never touched. The holdout on a FIXED population went from 90.306%
    // to 90.207% as a result. That is the whole mechanism by which R1 and P1
    // "poisoned" the fit, and it is not about density being bad in itself.
    const dense = r.dense === true;

    if ((r.state.springId || "").indexOf("3 3/4") !== 0) {
        continue;
    }

    readings.push({
        fromCorpus: true,
        noFit,
        dense,
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

// THE FITS MUST SEE THE DEDUPLICATED, HELD-OUT SET - so this runs HERE,
// before the per-rung groups below are built, and not after them.
//
// It used to sit further down, which meant the rungs - every K, every
// length, every band and line fitted from them - were collected from the
// RAW ingestion: 9452 entries against 4350 distinct. A reading held in both
// a pull and the corpus was therefore weighted TWICE in the fits, and only
// boundsFromSwitches, which is called after this block, ever saw the clean
// set. The two holdouts had the same problem the other way round: they
// withheld readings from an array the fits had already finished reading, so
// they withheld nothing that mattered and any generalisation number taken
// through them was fiction.
//
// This is what made the committed table unreproducible. Pull files are
// gitignored, so on a fresh build the duplicates are simply absent, the
// weighting changes, and apply.sh produces a different table from the one
// in git - 96.8% on the clean external readings against the 97.9% that was
// committed beside it.

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
// THE CORPUS WINS EVERY TIE, so the table cannot depend on which gitignored
// pull files happen to be on disk.
//
// Pull files are read first and the dedup keeps whichever copy it meets, so a
// reading held in both places was represented by its PULL copy - and once that
// pull is imported and then lost to a rebuild, the corpus copy takes over and
// the fit comes out different. The two are the same reading by every key the
// pipeline uses, which is why the distinct count does not move; they are not
// the same object.
//
// This was tried once before and appeared to do nothing, because at the time
// the fits were reading the raw ingestion from above the dedup entirely. With
// that fixed, this is what keeps the result stable.
const seenKey = new Map();
const collisions = [];
const unique = [];

readings.sort((a, b) => (b.fromCorpus ? 1 : 0) - (a.fromCorpus ? 1 : 0));

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

// HOLDOUT. Runs AFTER the dedup, for the same reason the hi-lift holdout
// below does: a reading arrives twice, once from its pull and once from the
// corpus, so withholding by index BEFORE dedup withholds one copy and leaves
// the other in the fit - scoring the model on data it still trained on. Any
// generalisation number taken that way is fiction.
//
// With HOLDOUT_MOD=n and HOLDOUT_REM=k every nth reading is withheld every nth reading is withheld from the fit, so
// the model can be scored on readings it never saw. Without it nothing is
// held back and the fit uses everything.
const HOLDOUT_MOD = Number(process.env.HOLDOUT_MOD || 0);
const HOLDOUT_REM = Number(process.env.HOLDOUT_REM || 0);

if (HOLDOUT_MOD > 1) {
    const kept = [];
    const held = [];

    readings.forEach((r, i) => {
        if (i % HOLDOUT_MOD !== HOLDOUT_REM) {
            kept.push(r);

            return;
        }

        const st = r.state;

        held.push([
            st.drum, st.springs, st.radius, st.liftType ?? "Standard",
            st.liftin ?? "", st.cycles, st.weight,
            st.doorHeightFeet, st.doorHeightInches ?? 0,
        ].join("|"));
    });

    console.error(`HELD ${held.length} of ${readings.length}`);

    for (const h of held) {
        console.error(`HELD\t${h}`);
    }

    readings.length = 0;
    readings.push(...kept);
}

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

// --- per rung: K from the cycle counts, thresholds from the lengths ---------
const rungs = new Map();
// See the CAP_RUNGS note below. Reproducible because `readings` is assembled in
// a fixed order from a fixed set of files, so "the first N" is the same N every
// run; this is an experiment knob, not a shipped feature, and defaults to off.
const CAP_RUNGS = new Set((process.env.CAP_RUNGS || "").split(",").map((x) => x.trim()).filter(Boolean));
// LENS_REPORT=1 prints how many LENGTH readings each rung has, which is the
// quantity the down-sampling experiment showed drives length accuracy - not
// the `n` in the table, which counts K readings and is much larger.
const LENS_REPORT = process.env.LENS_REPORT === "1";
const STIFFNESS_REPORT = process.env.STIFFNESS_REPORT === "1";
const UNFIT_RUNGS = new Set((process.env.ENABLE_UNFIT_RUNGS || "")
    .split(",").map((x) => x.trim()).filter(Boolean));
const CAP_N = Number(process.env.CAP_N) || 0;
const capSeen = new Map();
const CAP_SEED = Number(process.env.CAP_SEED) || 0;
// How many length readings each rung has in total, needed before the random
// subsample can know what fraction to keep. Filled by a first pass below.
const capTotal = new Map();

if (CAP_SEED) {
    for (const r of readings) {
        if (r.noFit || r.flagged) continue;

        const k = r.outer + "/" + r.inner;

        capTotal.set(k, (capTotal.get(k) || 0) + 1);
    }
}

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

    // Held out of the fit by corpus flag - see noFit above. It has already
    // served its purpose by winning the dedup against its own pull copy.
    //
    // ENABLE_UNFIT_RUNGS="a/b,c/d" admits those readings' LENGTHS back, on the
    // named rungs only. The experiment behind it: re-enabling U5-U8 wholesale
    // was measured at net -3 on the never-tuned draws (p = 0.607) and dropped,
    // but uniform data lands on rungs in proportion to how often a door hits
    // them - so it piles onto the four rungs already at 100% and barely touches
    // the thin ones. Down-sampling showed per-rung LENGTH volume is causal
    // (121/121 -> 107/121 by starving four rungs to 120 readings), so the
    // allocation, not the data, may have been what failed.
    //
    // K is left held out deliberately. Admitting it would move rung selection
    // and with it which readings have the wire right, and then the before/after
    // populations would not be the same readings.
    const unfitLenOk = r.noFit && UNFIT_RUNGS.has(key);

    if (r.noFit && !unfitLenOk) {
        continue;
    }

    if (r.cycles > 0 && !unfitLenOk) {
        const torque = (COEFF * Math.pow(r.inner, WEXP)) / Math.pow(r.cycles, 1 / CEXP);
        const body = divider(r.inner, 3.75) * c.turnsExact / torque;

        g.Ks.push(body * c.tipptExact / (springs / 2));
    }

    // rawActive is the formula's own value. The per-rung stiffness correction
    // is fitted after every rung is gathered, and `active` is then rewritten,
    // so the bands below fit whatever is LEFT rather than re-absorbing an
    // error the stiffness already explains.
    // A FLAGGED READING KEEPS ITS WIRE AND LOSES ITS LENGTH.
    //
    // The pairing above is as good as any - the reference picked it - and the
    // cycle count behind K with it. The LENGTH is the least trustworthy figure
    // in such a reading, because what the reference is usually complaining
    // about IS the length: past 120", past what the cones take, past what fits
    // the opening. Fitting the length model on those pulled it around for the
    // doors that can actually be built, which is what cost 2.7 points of
    // accuracy when batch L1's flagged half was included.
    //
    // Only readings imported after this flag existed carry it; the earlier
    // corpus has no flag and is fitted whole.
    if (r.flagged) {
        continue;
    }

    // The rounded TIPPT, matching duplexActiveLength: the reference computes
    // from the figure it displays, as it does for cycles and MIP.
    const shownTippt = Math.round(c.tipptExact * 10) / 10;
    // NO END COILS, matching duplexActiveLength - see the long note there. The
    // physics is confirmed and the coupling between the two nested springs is
    // not, so the term is left out of both rather than out of one.
    const rawActive =
        springs * (divider(r.inner, 3.75) + divider(r.outer, 6)) / shownTippt;

    // DOWN-SAMPLING EXPERIMENT, off unless asked for.
    //
    //   CAP_RUNGS="0.2625/0.2253,0.283/0.2343" CAP_N=120 sh dev/apply.sh
    //
    // Caps how many LENGTH readings a named rung may contribute, leaving its K
    // readings alone. The question it answers is causal: the never-tuned draws
    // show rungs with 300+ corpus readings at 100% and thinner rungs at 92.9%,
    // which either means data volume drives length accuracy - in which case a
    // rung-targeted pull is worth the rate limit - or means the well-covered
    // rungs are simply the easy ones a random door lands on. Starving a rich
    // rung down to a thin rung's volume separates the two for free.
    //
    // K is deliberately NOT capped. Capping it too would move rung selection,
    // and a drop caused by picking a different wire would look exactly like a
    // drop caused by worse thresholds.
    if (CAP_N && CAP_RUNGS.has(key)) {
        if (CAP_SEED) {
            // RANDOM subsample, not the first N. THIS MATTERS: the corpus is in
            // batch order and the early batches are deliberately
            // boundary-dense, so "the first N" keeps the most informative
            // readings and would misstate what losing data costs. A seeded
            // hash per reading gives a reproducible random subsample instead.
            // Both modes give the same dose-response, which is why the finding
            // is believed.
            let h = CAP_SEED;
            const id = key + "|" + r.id + "|" + JSON.stringify(r.state ?? {});

            for (let n = 0; n < id.length; n++) {
                h = (h * 31 + id.charCodeAt(n)) % 2147483647;
            }

            const total = (capTotal.get(key) || 0);

            if (total > CAP_N && (h % total) >= CAP_N) {
                continue;
            }
        } else {
            capSeen.set(key, (capSeen.get(key) || 0) + 1);

            if (capSeen.get(key) > CAP_N) {
                continue;
            }
        }
    }

    g.lens.push({
        springs, rawActive, length: r.length, dense: r.dense === true,
        active: rawActive,
        frac: rawActive - Math.floor(rawActive),
        bonus: Number((r.length - Math.floor(rawActive)).toFixed(2)),
    });
}

if (LENS_REPORT) {
    const rows = [...rungs].map(([key, g]) => [key, g.lens.length, g.Ks.length])
        .sort((a, b) => b[1] - a[1]);

    process.stderr.write("rung             lens     Ks\n");

    for (const [key, lens, ks] of rows) {
        process.stderr.write(`${key.padEnd(15)}${String(lens).padStart(5)}  ${String(ks).padStart(5)}\n`);
    }

    process.stderr.write(`total lens ${rows.reduce((a, b) => a + b[1], 0)} over ${rows.length} rungs\n`);
}

// Fit the stiffness correction per rung, then restate every active length and
// bonus through it.
for (const g of rungs.values()) {
    // ONLY SPRINGS THE REFERENCE WILL BUILD. Readings needing more than 120"
    // are refused by the reference ("Only spring lengths between 0 and 120 are
    // supported") and run to 420" in the corpus, so letting them into the
    // stiffness fit drags it badly - they are the readings furthest from any
    // grid and they outvote the real ones on the softest rungs.
    const usable = g.lens.filter(
        (l) => l.rawActive > 0 && l.length > 0 && l.length <= 120
    );

    // The stiffness is fitted from ORDINARY doors only - see `dense` above. The
    // boundary-dense readings stay in `g.lens` and so still reach the band and
    // threshold fitters further down, which is the only place they belong.
    const forStiffness = usable.filter((l) => !l.dense);

    g.sMult = 1;

    // STIFFNESS_REPORT=1 asks whether sMult should be fitted per SPRING COUNT
    // instead of per rung. It measures and changes nothing.
    //
    // IT SAID YES AND IT WAS WRONG - keep this, and keep reading. Over the 35
    // rungs with 40+ readings:
    //
    //                      in sample   five-fold CV
    //   one m per rung         6673         6551
    //   one m per count        6948         6831
    //
    // An out-of-fold gain (+280) larger than the in-sample one (+275) is
    // normally conclusive. Built properly - per-count m in the table, the
    // component picking by spring count, the bands refitted against the same
    // multiplier - the never-tuned draws went from 340/347 to 339/347. ONE
    // READING WORSE.
    //
    // The reason is that this measures a stage in isolation, and the stage
    // below it already does the job: lineByCount and byCount are keyed by
    // SPRING COUNT, so the thresholds were already absorbing the per-count
    // variation. The CV counted a gain the pipeline already had.
    //
    // The lesson is not about stiffness. It is that a fitter stage cannot be
    // scored on its own when a later stage can compensate for it - only the
    // whole pipeline, against data nothing was tuned on, settles anything.
    if (STIFFNESS_REPORT && forStiffness.length >= 40) {
        const whole = fitStiffness(forStiffness);
        const counts = [...new Set(forStiffness.map((l) => l.springs))].sort();
        let perCountOk = 0;
        const ms = [];

        for (const sp of counts) {
            const rows = forStiffness.filter((l) => l.springs === sp);
            const f = rows.length >= 8 ? fitStiffness(rows) : null;

            perCountOk += f ? f.ok : 0;
            ms.push(`${sp}:${f ? f.m.toFixed(4) : "-"}(${rows.length})`);
        }

        const cv = (mode) => {
            let ok = 0;

            for (let k = 0; k < 5; k++) {
                const train = forStiffness.filter((_, i) => i % 5 !== k);
                const test = forStiffness.filter((_, i) => i % 5 === k);

                for (const l of test) {
                    const rows = mode === "count"
                        ? train.filter((t) => t.springs === l.springs)
                        : train;
                    const f = rows.length >= 8 ? fitStiffness(rows) : fitStiffness(train);

                    if (f && Math.abs(
                        snapGrid(l.rawActive * f.m, l.springs, f.twoOffset) - l.length
                    ) < 1e-9) {
                        ok += 1;
                    }
                }
            }

            return ok;
        };

        process.stderr.write(
            `${(g.outer + "/" + g.inner).padEnd(14)} n=${String(forStiffness.length).padStart(4)}`
            + `  rung m=${whole.m.toFixed(4)} ok=${String(whole.ok).padStart(4)}`
            + `  perCount ok=${String(perCountOk).padStart(4)}`
            + `  CV rung=${String(cv("rung")).padStart(4)} CV count=${String(cv("count")).padStart(4)}`
            + `  [${ms.join(" ")}]\n`
        );
    }

    if (forStiffness.length >= 12) {
        const fit = fitStiffness(forStiffness);

        if (fit && fit.ok > 0) {
            g.sMult = Number(fit.m.toFixed(6));
            g.twoOffset = fit.twoOffset;
        }
    }

    for (const l of g.lens) {
        l.active = l.rawActive * g.sMult;

        const whole = Math.floor(l.active);

        l.frac = l.active - whole;
        l.bonus = Number((l.length - whole).toFixed(2));

        // ONLY READINGS THE BAND MODEL CAN REPRESENT. The stiffness fit above
        // already drops the over-120" readings the reference refuses to build,
        // but the band fitter was still shown every one of them, and it duly
        // memorised them: the shipped table carried bonuses of -24.25, +7 and
        // -8.75 inches. Those are not rounding corrections. They are single
        // readings where the active length is wildly wrong, written into a
        // frac band that then answers for every unseen door landing in the
        // same sliver of frac.
        //
        // Two conditions, both from the reference's own behaviour:
        //
        //   ON THE LATTICE. Every length the reference quotes is a whole inch
        //   or a whole inch plus a quarter - 1178 of 1178 springs across the
        //   external samples, inner and outer alike, with .5 and .75 appearing
        //   only in the runaway cases excluded here. The bonus is measured
        //   from an integer floor, so its own fraction must be 0 or 0.25.
        //
        //   WITHIN REACH. A bonus is the gap between the reference's length
        //   and our floor; one bigger than 1.25" is not a grid offset, it is
        //   the model being wrong by inches.
        //
        // Pruning these lifted the external clean length from 90.3% to 91.2%
        // and within-1" from 97.9% to 98.6%, with flagged readings up too, so
        // this is not a trade.
        const bonusFrac = ((l.bonus % 1) + 1) % 1;

        l.ok =
            l.rawActive > 0 &&
            l.length > 0 &&
            l.length <= 120 &&
            Math.abs(l.bonus) <= 1.25 &&
            (bonusFrac < 1e-9 || Math.abs(bonusFrac - 0.25) < 1e-9);
    }
}

// THE EFFECTIVE STIFFNESS OF A RUNG, MEASURED RATHER THAN COMPUTED.
//
// duplexActiveLength is springs * S / TIPPT with S the sum of the two
// dividers. Because the reference reports BOTH its length and its TIPPT, S can
// be solved from each reading: S = length * TIPPT / springs. Doing that across
// every reading on a rung and taking the median shows the computed S is wrong
// by up to 4.6%, and differently per rung:
//
//   0.2625/0.2253   computed 1015   implied 1062   +4.6%
//   0.3625/0.283    computed 4217   implied 4124   -2.2%
//   0.4375/0.3625   computed 11800  implied 12156  +3.0%
//
// On a 20" spring 4.6% is nearly an inch, which is exactly the error the bands
// were absorbing. One number per rung fixes the cause instead.
//
// PER RUNG, NOT PER (RUNG, SPRING COUNT). Stiffness is a property of the wire
// pair, so the spring count has no business in it - and the measurement agrees:
// per rung scores 76.3% on the external samples against 79.0% in sample for
// the per-count version but only 75.5% external, with eight times fewer unseen
// groups. Fewer parameters, better generalisation, right physics.
//
// The multiplier is searched rather than taken from the median because what
// matters is landing on the right side of the grid, not minimising residual.
// MAX MARGIN IS FOR A DECISION BOUNDARY, NOT FOR A SCALE. Measured, reverted.
//
// Every threshold fitter in this file was changed today to choose for margin
// instead of for a count, and it was the clearest gain of the session. The same
// change here - break the plateau in `ok` by preferring the multiplier whose
// correct readings sit furthest from snapping somewhere else - moved sMult on 15
// of 50 rungs and cost 7 readings on the five-fold holdout at a fixed population,
// 90.554% to 90.463%. It also agrees with an earlier, weaker attempt to centre
// sMult in its plateau, which bought 2 readings in 5,157 and nine extra bands.
//
// THE ANALOGY FAILS, AND IT IS WORTH KNOWING WHY. A threshold's position is
// unknown and the data only brackets it, so sitting in the middle of the bracket
// is the minimax guess and robustness is the whole game. A stiffness is not a
// boundary: it is a physical scale, and where a reading falls inside its grid
// cell is determined by the spring, not by noise. Pushing readings toward the
// centres of their cells therefore biases the scale to make the data look tidy -
// it is fitting a property the reference does not have.
//
// So the plateau stays broken by taking the lowest multiplier that achieves it.
// That is arbitrary, and measurably better than the principled-sounding
// alternative.
function fitStiffness(ls) {
    let best = null;

    // The stiffness and the two-spring offset are fitted together, because the
    // offset shifts where the grid falls and the stiffness shifts what lands
    // on it - picking either alone picks it against the wrong grid.
    for (const twoOffset of [0, 0.25]) {
        for (let bi = -320; bi <= 320; bi += 1) {
            const m = 1 + bi / 4000;         // +-8% in 0.025% steps
            let ok = 0;

            for (const l of ls) {
                if (Math.abs(
                    snapGrid(l.rawActive * m, l.springs, twoOffset) - l.length
                ) < 1e-9) {
                    ok += 1;
                }
            }

            if (!best || ok > best.ok) {
                best = { ok, m, twoOffset };
            }
        }
    }

    return best;
}

// 1 spring is whole inches (1843 of 1843 readings), 3 and 4 springs are whole
// plus a quarter (594 and 413 of each), and 2 springs uses both - 793 at .0 and
// 274 at .25, never .5 or .75. So 2 springs snaps to whichever of {N, N+0.25}
// is nearer, which is deterministic; there is no free choice to exploit.
function snapGrid(x, springs, twoOffset) {
    if (springs === 1) {
        return Math.round(x);
    }

    if (springs >= 3) {
        return Math.round(x - 0.25) + 0.25;
    }

    // TWO SPRINGS TAKES ITS OFFSET FROM THE RUNG. It uses .0 on 799 readings
    // and .25 on 276, never .5 or .75, and the RUNG alone predicts which on
    // 86.4% of them - 42 buckets over 1075 readings. Snapping to whichever is
    // nearer instead was the single biggest source of error on the readings
    // the reference answers cleanly.
    const off = twoOffset === undefined ? 0 : twoOffset;

    return Math.round(x - off) + off;
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
        // The lift MUST be part of the key. A switch point is "the heaviest
        // door still on this rung, and the next one up" - which only means
        // anything if the two readings differ in weight alone. Leaving the
        // hi-lift amount out grouped D800-120 3-spring readings at 900 lb
        // with hiLift 12, 24, 72 and 96 into one sequence: same weight,
        // different wire, recorded as a switch at a weight delta of zero.
        //
        // That single bogus switch put the hi bound for rung 0.3625/0.283 at
        // 6565.7 while every real bound on it sits at 7482-7495, which is
        // what made the rung's bounds unsatisfiable.
        const key = [st.drum, st.springs, st.radius, st.doorHeightFeet,
                     st.doorHeightInches, st.cycles,
                     st.liftType ?? "Standard", st.liftin ?? ""].join("|");

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
                out.set(ka, { lo: [], hi: [], loSrc: [], hiSrc: [] });
            }

            for (const [side, reading] of [["lo", a], ["hi", b]]) {
                const c = make(mod, reading.state);

                // duplexTipptExact, NOT tipptExact: the latter is the Single
                // path's, computed on the entered weight with no drum cap.
                // D400-144 is rated 750 lb and the corpus has a 765 lb
                // reading, so the unclamped figure is a weight the reference
                // threw away before it picked anything.
                if (!c.duplexTipptExact || !c.turnsExact) {
                    continue;
                }

                out.get(ka)[side].push(
                    divider(a.inner, 3.75) * c.turnsExact * c.duplexTipptExact /
                    (torque * (springs / 2))
                );
                // Keep WHICH reading set each bound. When a rung's bounds
                // cannot all hold, the only useful question is which reading
                // disagrees with the rest, and that is unanswerable from the
                // numbers alone.
                out.get(ka)[side + "Src"].push(
                    `${reading.state.drum.split(" ").pop()} ${reading.state.weight}lb ` +
                    `${reading.state.doorHeightFeet}'${reading.state.doorHeightInches || 0}" ` +
                    `${reading.state.springs}spr r${reading.state.radius} t${reading.state.cycles}`
                );
            }
        }
    }

    return out;
}


const switchBounds = boundsFromSwitches(readings);

const median = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);

    return s[Math.floor(s.length / 2)];
};

const contradictions = [];
const overfit = [];
const MAX_BANDS = Number(process.env.MAX_BANDS || 64);

// HOW FINELY THE THRESHOLD SLOPE IS SCANNED. b runs over +-BLO/B_STEPS in steps
// of 1/B_STEPS, so 2000 is a step of 0.0005 over a range of +-0.25.
//
// It is a shared constant rather than two copies of a literal because the two
// fitters have to agree: a slope one of them can express and the other cannot
// would make the choice between their forms depend on the grid rather than on
// the fit.
const B_STEPS = Number(process.env.B_STEPS || 2000);


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
// THE THRESHOLD IS LINEAR IN THE INTEGER PART OF THE ACTIVE LENGTH.
//
// The band model keyed the bonus on frac(active) alone, and that provably
// cannot work. On 0.3625/0.283 at one spring, frac 0.815 wants +1 at active
// 17.815 and 0 at active 25.816: same rung, same spring count, same frac,
// different answer. What separates them is the integer part, and the threshold
// moves with it - on that rung the bonus flips at about 0.80 at floor 17, 0.84
// at floor 18, 0.91 at floor 24 and never by floor 25.
//
// So the rule is a line, t = a + b*floor, and the bonus steps up where frac
// crosses it. Two parameters, against the eighteen alternating bands the frac
// fitter wanted on 0.375/0.295 - which fit their readings and predicted
// nothing.
//
// TWO PARALLEL THRESHOLDS for a group with three bonus levels. They share one
// slope and differ only in intercept, so a third level costs one parameter,
// not another whole line. The rungs that need it are the ones whose bonus
// reaches -1 as well as 0 and +1, 0.3625/0.283 at one spring among them.
//
// HOW IT IS FITTED. For a fixed slope b, write u = frac - b*floor; every
// threshold is then a constant in u, so the readings sorted by u must come
// out in bonus order - lowest bonus first - and fitting reduces to choosing
// one or two cut points in that sorted list. That is exact and cheap, where
// searching the intercepts directly is a three-dimensional grid. Only the
// slope is searched.
// A REGIME BOUNDARY IN THE ACTIVE LENGTH, where the data shows one.
//
// Some three-level groups are not one rule with three levels; they are two
// rules with two levels each, split at an active length. On 0.3625/0.283 at
// one spring the -1 bonus appears at floor 29 and above and NEVER below it,
// and a single threshold line fits each side on its own - 136 readings below,
// 33 above. The softest rung has had exactly this shape hand-maintained as
// `long: { from: 25.5 }` since before any of the fitting existed, so the
// structure is not invented here.
//
// WHY THIS IS NOT THE TWO-THRESHOLD FORM AGAIN. That one put two thresholds
// over the SAME readings, so one slope had to serve every active length and a
// small error in it misplaced predictions far from where it was fitted - 894
// readings moving together, holdout 97.4% -> 84.9%. Here each line owns a
// disjoint, contiguous range of floor, so it is constrained locally, the way
// a band is. The breakpoint is read off the data (the first floor at which
// the lowest bonus occurs) rather than fitted.
//
// WHICH FORM GENERALISES, DECIDED PER GROUP BY CROSS-VALIDATION.
//
// The two-threshold line is not automatically an improvement. Switched on for
// every three-level group it raised in-sample accuracy from 99.0% to 99.6%
// and dropped OUT-OF-SAMPLE accuracy from 97.4% to 84.9% - 894 readings sit
// under those seven groups, and the fit is not unique on them: many
// (b, a, a2) reach zero violations, each fold picks a different one, and the
// one it picks mispredicts the fold it never saw. On 0.4305/0.3625 the slope
// came out at exactly -0.03, the edge of the search, which is the fitter
// telling you it is not determined.
//
// So neither form is assumed. Each group holds out a fifth of its own
// readings five times, scores the line and the bands on readings each never
// saw, and keeps whichever wins - the line only on a strict win, since it is
// the stronger structural claim. A group whose line is genuinely the rule
// wins easily; a group whose line is one of many equally good fits loses,
// which is exactly what should happen.
function cvScore(ls, fit, predict) {
    let right = 0;
    let total = 0;

    for (let k = 0; k < 5; k++) {
        const train = ls.filter((_, i) => i % 5 !== k);
        const test = ls.filter((_, i) => i % 5 === k);

        if (!train.length || !test.length) {
            continue;
        }

        const model = fit(train);

        if (!model) {
            return -1;
        }

        for (const l of test) {
            total += 1;
            right += predict(model, l.active) === l.bonus ? 1 : 0;
        }
    }

    return total ? right / total : -1;
}

function bandPredict(bs, active) {
    const frac = active - Math.floor(active);

    for (const b of bs) {
        if (frac < b.upTo) {
            return b.bonus;
        }
    }

    return Math.round(active) - Math.floor(active);
}

function linePredict(line, active) {
    const whole = Math.floor(active);
    const frac = active - whole;
    const first = line.a + line.b * whole;

    if (line.mid !== undefined) {
        // b2 only where the thresholds were fitted on their own slopes.
        const second = line.a2 + (line.b2 ?? line.b) * whole;

        return frac > second ? line.hi : frac > first ? line.mid : line.lo;
    }

    return frac > first ? line.hi : line.lo;
}

// DEFAULT 2: SINGLE THRESHOLDS ONLY. The two-threshold form is implemented
// and switchable with LINE_LEVELS=3, and it is OFF because it was measured,
// not because it was untried:
//
//                              in sample   out of sample
//   single threshold only        99.0%         97.4%
//   two thresholds, all groups   99.6%         84.9%
//   two thresholds, per-group CV 99.4%         88.5%
//
// It fits better and predicts worse, which is the definition of the thing to
// avoid. Letting each group choose by its own cross-validation recovered half
// the loss and still lost - a group can win a local comparison and damage the
// whole-corpus holdout, because the choice was made on data the holdout then
// scores.
//
// WHY BANDS BEAT IT, which is worth writing down because it is not obvious
// that 33 bands should generalise better than 3 parameters: a band is LOCAL.
// A held-out reading falls in a band pinned by the readings either side of
// it, so an error stays where it is. A line is GLOBAL - one slightly wrong
// slope misplaces every prediction far from where it was fitted at once. On
// the three-level groups the fit is not even unique (0.4305/0.3625 came out
// at exactly -0.03, the edge of the search), so each fold picks a different
// slope and the 894 readings under those groups move together.
//
// Single thresholds stay on: there the line is strictly simpler than any band
// arrangement that fits, and the holdout agrees.
// THE BREAKPOINT IS SEARCHED, NOT ASSUMED. It was taken to be the floor where
// the lowest bonus first appears, which is only one candidate and only worked
// for three groups. Scanning every floor finds breakpoints for three more:
// 0.4305/0.3625 and 0.375/0.3065 at one spring, and 0.4375/0.3625 at 51.
//
// SEVERAL BREAKPOINTS OFTEN WORK - 0.4305/0.3625 fits at 29, 30, 32 and 37 -
// so the breakpoint is underdetermined, and picking one arbitrarily is exactly
// what made the two-threshold form unstable. Each group therefore chooses by
// its own cross-validation, scoring candidates on readings the fit never saw,
// and ties go to the most balanced split because that is the best-determined
// one. A group that cannot beat its own bands keeps them.
//
// Both sides must carry at least twelve readings; a trivial side is noise with
// a breakpoint attached.
function fitSplit(ls) {
    const vals = [...new Set(ls.map((l) => l.bonus))].sort((x, y) => x - y);

    if (vals.length < 2) {
        return null;
    }

    // EACH SIDE GETS UP TO THREE LEVELS, two preferred.
    //
    // Both sides used to be capped at two, which meant a group whose regimes
    // have DIFFERENT level counts could never produce a viable split - one
    // side came back null and the candidate was dropped. 0.2625/0.2253 at two
    // springs is exactly that, and it carries half of what the model still
    // gets wrong. A fraction walk of it, laid out by the integer part, shows
    // two regimes rather than one rule with three levels:
    //
    //   floors 15-23   three bands:  0.25 low frac, 0 middle, 1.25 high
    //   floors 24+     two bands:    0.25 low and middle, 1.25 high
    //
    // The 0 level simply does not exist above floor 23. With both sides capped
    // at two the lower regime was unfittable, no split was offered, and the
    // group fell through to memorising 42 bands.
    //
    // Two is tried first so the simpler side wins when it can, and the whole
    // split is still cross-validated against the bands below - a three-level
    // side only survives if the split as a whole predicts better out of
    // sample than the band table it would replace.
    // A SIDE MAY ALSO NEED ITS THRESHOLDS ON SEPARATE SLOPES. Two preferred,
    // then three sharing a slope, then three on their own.
    //
    // 0.273/0.2253 at two springs is the case that wanted the last option. It
    // is two regimes of three levels each, split near floor 20:
    //
    //   floors 10-19   0 low and middle, 1.25 at 0.76-0.95, 1 above 0.91
    //   floors 20+     0.25 below ~0.08, 0 in the middle, 1.25 above ~0.76
    //
    // On the upper side the low threshold CLIMBS with the integer part - 0.01
    // at floor 20, 0.11 by 26 - while the high one sits flat near 0.76. Forced
    // to share a slope neither can be placed, no split was viable, and the
    // group kept a band table while its misses piled up at floors 16 to 23,
    // right where the regimes meet.
    // BEST FIT WINS, SIMPLEST ON A TIE - not whichever was tried first.
    //
    // Taking the first form that fitted meant a shared slope beat independent
    // ones whenever it merely came inside the slack, even where the data says
    // the thresholds move apart. On the upper regime of 0.273/0.2253 at two
    // springs that produced `b: 0.014` shared between both thresholds, which
    // drags the high one from 0.65 at floor 20 to 0.73 by floor 26 when the
    // readings put it flat near 0.76 throughout.
    //
    // The forms are listed simplest first and a later one has to be STRICTLY
    // better to displace an earlier one, so nothing gains freedom it does not
    // pay for.
    const sideLine = (rows) => {
        let best = null;

        for (const cand of [fitLineAnyOrder(rows, 2), fitLineAnyOrder(rows, 3),
                            fitLineOwnSlopes(rows, 3)]) {
            if (cand && (!best || cand.bad < best.bad)) {
                best = cand;
            }
        }

        return best;
    };

    const floors = [...new Set(ls.map((l) => Math.floor(l.active)))]
        .sort((x, y) => x - y);
    const viable = [];

    for (const from of floors) {
        const below = ls.filter((l) => Math.floor(l.active) < from);
        const above = ls.filter((l) => Math.floor(l.active) >= from);

        // 8, RE-MEASURED for the same reason: a split needed twelve readings
        // either side of the break, which was a twenty-fourth of the old
        // duplicated ingestion and is a twelfth of what a group holds now, so
        // splits that are real were being refused for want of data:
        //
        //   SPLIT_MIN_SIDE   bands   clean   flagged
        //         4            28    97.2%   85.0%
        //         6            31    97.4%   85.0%
        //         8            38    97.7%   85.3%
        //        12            71    96.8%   84.4%
        //        20            90    96.5%   84.4%
        //
        // Measured together with LEVEL_SUPPORT, since both decide whether a
        // group gets a model or a band table. The holdout moved 92.3% to
        // 92.4%, which looked like confirmation at the time and was really the
        // size of the effect: a fresh uniform sample shows no gain from any of
        // these three knobs. See the note on LINE_SLACK. Kept because at equal
        // honest accuracy it is the smaller model.
        const minSide = Number(process.env.SPLIT_MIN_SIDE || 8);

        if (below.length < minSide || above.length < minSide) {
            continue;
        }

        const b = sideLine(below);
        const a = sideLine(above);

        if (b && a) {
            viable.push({ from, below: b, above: a, balance: Math.min(below.length, above.length) });
        }
    }

    if (!viable.length) {
        return null;
    }

    let best = null;

    for (const cand of viable) {
        const score = cvScore(
            ls,
            (train) => {
                const b = sideLine(train.filter((l) => Math.floor(l.active) < cand.from));
                const a = sideLine(train.filter((l) => Math.floor(l.active) >= cand.from));

                return b && a ? { from: cand.from, below: b, above: a } : null;
            },
            (model, active) => linePredict(
                Math.floor(active) >= model.from ? model.above : model.below,
                active
            )
        );

        if (!best || score > best.score ||
            (score === best.score && cand.balance > best.balance)) {
            best = { ...cand, score };
        }
    }

    return best;
}

// DEFAULT 2, measured. The K-level fitter below handles any number of
// parallel thresholds and is left in place, but on the external random sample
// (seed 777001, never fitted) more levels do not pay:
//
//   LINE_LEVELS   corpus      external sample   softest rung
//       2         3153/3181      158/239           58.3%
//       3         3154/3181      157/239           58.3%
//       4         3154/3181      157/239           58.3%
//
// One corpus reading bought, one external reading lost. The softest rung -
// which genuinely does take four bonus values, so this was aimed straight at
// it - does not move at all. Added freedom that does not improve the honest
// score is not worth carrying.
//
// RE-MEASURED 2026-10-05, after the fitter stopped requiring the bands to run
// in bonus order and gained a 3% error budget - both of which let far more
// groups take a line, so the old measurement could no longer be assumed:
//
//                    clean    within 1"   flagged
//       2 levels      94.7%     99.1%      83.1%
//       3 levels      94.7%     99.1%      82.5%
//
// Identical on the readings that get ordered and half a point worse on the
// flagged ones, with 68 bands against 71 - so the extra freedom buys three
// bands' worth of tidiness and costs accuracy. Still 2.
const LINE_LEVELS = Number(process.env.LINE_LEVELS || 2);

function fitLine(ls) {
    return fitLineAnyOrder(ls, LINE_LEVELS);
}

// K PARALLEL THRESHOLDS, all sharing one slope.
//
// The bonus on a rung does not take two values. On 0.2625/0.2253 at three and
// four springs - the single biggest group in the allowed box, 25% of
// everywhere a random door lands, and the least accurate at 55.6% - it takes
// FOUR: 0.25, 1.25, 2.25 and 3.25. Those are lo + k for integer k, which is
// what parallel thresholds mean. One slope plus K-1 intercepts, so a fourth
// level costs one number rather than another line.
//
// WHY THIS IS NOT THE TWO-THRESHOLD FORM ALREADY REJECTED. That was fitted on
// groups holding 21 readings on average, where many (slope, cuts) reach zero
// violations, each fold picks a different one, and 894 readings moved together
// - the holdout fell 97.4% to 84.9%. This group now holds 132 and 173 readings
// from a dense walk of the fraction, which is what makes the cuts determined.
// The arbiter is the EXTERNAL random sample, not a local cross-validation: a
// group can win locally and lose globally, which is exactly what that attempt
// did.
//
// For a fixed slope, u = frac - b*floor turns every threshold into a constant,
// so readings sorted by u must come out in bonus order and fitting reduces to
// choosing K-1 cut points. That is a dynamic program over (level, position).
function fitLineAnyLevels(ls, maxLevels) {
    // A LEVEL SUPPORTED BY ONE READING IN SIXTY IS NOT A LEVEL.
    //
    // The level count alone decided whether a group got a two-parameter line
    // or a band table, and one stray reading was enough to tip it. On
    // 0.2625/0.2253 at two springs, a fraction walk of 60 readings came back
    // {0.25: 43, 1.25: 16, 0: 1} - a clean two-level line with a threshold
    // near 0.74, plus a single reading at frac 0.728 that wanted 0. That one
    // reading made the group "three-level", the line was refused, and the
    // fitter memorised FORTY-TWO bands instead. The same rung's three-spring
    // group, which happens to have no such outlier, got a line at 0.747 that
    // explains all 60 of its readings.
    //
    // So levels are counted with the stragglers dropped, and the line is
    // fitted to the rest. It will then get that one reading wrong, which is
    // the right trade: one miss against 42 bands of memorised noise.
    //
    // THIS CANNOT QUIETLY MAKE THINGS WORSE. The caller cross-validates the
    // line against the bands over ALL the readings, outlier included, and
    // keeps the bands unless the line wins out of sample. Dropping a level
    // here only lets the line be CONSIDERED; it still has to earn the place.
    const support = new Map();

    for (const l of ls) {
        support.set(l.bonus, (support.get(l.bonus) || 0) + 1);
    }

    // 0.06, RE-MEASURED after the fits stopped seeing duplicates - 3% of a
    // group that had just halved was too small a bar, so levels that are
    // really noise survived and kept pushing groups off the line fitter:
    //
    // THESE FIGURES DO NOT SURVIVE A FRESH SAMPLE - see the note on LINE_SLACK.
    // 0.06 is kept for parsimony at equal honest accuracy, not because it
    // scores better.
    //
    //   LEVEL_SUPPORT   clean length on the samples it was tuned against
    //       0.01           96.8%
    //       0.03           96.8%
    //       0.06           97.2%
    //       0.10           97.2%
    const floor = Math.max(2, Math.ceil(ls.length * Number(process.env.LEVEL_SUPPORT || 0.06)));
    const solid = new Set([...support].filter(([, n]) => n >= floor).map(([v]) => v));
    const used = solid.size >= 2 && solid.size < support.size
        ? ls.filter((l) => solid.has(l.bonus))
        : ls;

    const vals = [...new Set(used.map((l) => l.bonus))].sort((x, y) => x - y);

    if (vals.length < 2 || vals.length > maxLevels) {
        return null;
    }

    const K = vals.length;
    const cls = new Map(vals.map((v, i) => [v, i]));
    const pts = used.map((l) => ({
        F: Math.floor(l.active),
        t: l.active - Math.floor(l.active),
        c: cls.get(l.bonus),
    }));
    let best = null;

    // THE SLOPE RANGE HAS TO CONTAIN THE ANSWER. It was [-0.03, 0.09], and
    // slopes piled up on exactly -0.03000 - which meant the true value lay
    // past the edge, not that it was undetermined. A dense walk of the
    // fraction on 0.2625/0.2253 at three springs puts the threshold between
    // 0.173 and 0.281 at floor 11, between 0.056 and 0.204 at 13, and below
    // 0.048 by 19: a slope near -0.045.
    for (let bi = Number(process.env.BLO || -500); bi <= Number(process.env.BHI || 500); bi += 1) {
        const b = bi / B_STEPS;
        const sorted = pts
            .map((p) => ({ u: p.t - b * p.F, c: p.c }))
            .sort((x, y) => x.u - y.u);
        const n = sorted.length;
        const wrong = [];

        for (let k = 0; k < K; k++) {
            const row = new Array(n + 1).fill(0);

            for (let i = 0; i < n; i++) {
                row[i + 1] = row[i] + (sorted[i].c === k ? 0 : 1);
            }

            wrong.push(row);
        }

        const span = (k, i, j) => wrong[k][j] - wrong[k][i];
        let dp = new Array(n + 1);
        const from = [];

        for (let i = 0; i <= n; i++) {
            dp[i] = span(0, 0, i);
        }

        for (let k = 1; k < K; k++) {
            const next = new Array(n + 1).fill(Infinity);
            const pick = new Array(n + 1).fill(0);

            for (let i = 0; i <= n; i++) {
                for (let j = 0; j <= i; j++) {
                    const cost = dp[j] + span(k, j, i);

                    if (cost < next[i]) {
                        next[i] = cost;
                        pick[i] = j;
                    }
                }
            }

            from.push(pick);
            dp = next;
        }

        const bad = dp[n];

        // A strictly worse slope can go before the cuts are even rebuilt.
        if (best && bad > best.bad) {
            continue;
        }

        const cuts = [];
        let at = n;

        for (let k = K - 2; k >= 0; k--) {
            at = from[k][at];
            cuts.unshift(at);
        }

        const cutAt = (i) =>
            i === 0 ? sorted[0].u - 1e-6
                : i === n ? sorted[n - 1].u + 1e-6
                    : (sorted[i - 1].u + sorted[i].u) / 2;

        // AMONG EQUALLY GOOD SLOPES, THE ONE WITH THE MOST ROOM - and for a
        // rule with several parallel cuts the room it has is its TIGHTEST cut,
        // because that is the one a new reading flips first.
        //
        // This preferred the flattest slope, on the reasoning that a flat line
        // claims least off the end of the data. That is a real consideration
        // and it is now the second tie-break, but it was deciding cases where
        // a slightly steeper line held the same readings apart with a much
        // wider gap. The single-threshold fitter was changed the same way and
        // gained 0.3 points of held-out accuracy on its own.
        //
        // A cut below or above everything scores zero room on purpose: it
        // predicts one class for the whole group and has unbounded space on one
        // side, so it must never win a tie on margin.
        // CAPPED AT THE WIDTH OF THE RANGE A FRACTION CAN OCCUPY.
        //
        // The margin is a distance in frac, and frac lives in [0, 1). A gap
        // wider than that means the threshold line has left the band the data
        // occupies altogether: it is no longer separating readings by their
        // fraction, it is separating them by their floor, with the fraction
        // playing no part. There is no more information in being three units
        // outside the range than in being one, so there is no more credit.
        //
        // Without the cap the reward grows with the slope and the scan runs to
        // whatever bound it is given - 16 of 136 lines came back sitting exactly
        // on it, at a slope 250 times the median, where before this objective
        // there were none at all. A group that really does switch on the floor
        // has `splitByCount` for it, fitted as a floor boundary rather than
        // smuggled in as a near-vertical threshold.
        //
        // At the cap, ties fall through to the flatness preference below, which
        // picks the gentlest line that separates the readings completely.
        const gapAt = (i) =>
            i <= 0 || i >= n ? 0 : Math.min(sorted[i].u - sorted[i - 1].u, 1);
        const margin = cuts.length ? Math.min(...cuts.map(gapAt)) : 0;

        const better = !best || bad < best.bad
            || margin > best.margin + 1e-12
            || (Math.abs(margin - best.margin) <= 1e-12 && Math.abs(b) < Math.abs(best.b));

        if (!better) {
            continue;
        }

        best = { bad, b, a: cuts.map(cutAt), margin };
    }

    // A LINE THAT GETS 98 OF 100 RIGHT IS STILL A BETTER MODEL THAN 42 BANDS.
    //
    // This demanded a PERFECT fit, which is reasonable on a group of twelve
    // readings and brittle on one of two hundred: a single anomalous reading
    // was enough to reject the line and send the group to a band table that
    // then memorised the anomaly along with everything else. Same failure as
    // the straggler rule above, one level down.
    //
    // The budget is 3% of the group, so small groups still need to be exact
    // (under 34 readings the allowance rounds to zero) and large ones are
    // allowed a couple of misfits. The caller still cross-validates the line
    // against the bands and keeps the bands unless the line predicts better
    // out of sample, so this cannot trade accuracy for tidiness.
    // 0.08, RE-MEASURED after the fits stopped seeing duplicates. It was 0.03,
    // chosen when the fits read the raw 9452-entry ingestion; deduplicating
    // roughly halved what each group holds, so the same fraction became a much
    // smaller absolute allowance and groups that had been fitted as lines fell
    // back to bands.
    //
    //   LINE_SLACK   bands   clean length   five-fold holdout
    //      0.03       119       94.7%           92.1%
    //      0.08        71       96.8%           92.3%
    //      0.12        71       96.8%            -
    //
    // Flat from 0.08 to 0.12 rather than a knife edge, fewer bands, and better
    // on both measures.
    //
    // 0.18, RE-MEASURED AGAIN 2026-10-07 after the threshold fitters started
    // choosing their slope for margin. This knob says how wrong a line may be
    // before its group falls back to a band table, so improving the line fitter
    // moves it - and it had been set twice against a fitter that no longer
    // exists.
    //
    //   LINE_SLACK   bands   five-fold holdout
    //      0.12        48         90.21%
    //      0.15         -         90.22%
    //      0.18        31         90.31%
    //      0.20         -         90.26%
    //      0.25         -         90.18%
    //
    // A gentle plateau at 0.18-0.20 rather than a spike, and the whole range
    // spans 0.13 points - so this knob matters much less than it did, which is
    // itself worth knowing. 0.18 is taken because the holdout prefers it AND it
    // carries 17 fewer memorised bands: on the external samples a band table
    // scores 83-94% where a line scores 96-97%, so moving groups off bands is
    // the same direction the accuracy moved.
    //
    // The sweep that found 0.08 read 96.8% and a clean re-derive then read
    // 96.3%, which I first put down to the sweep scoring leftover tables. That
    // was wrong. The sweep passed LINE_SLACK as an ENV VAR, which reached both
    // fitters; raising only this default left fitLineOwnSlopes on 0.03. With
    // the two sharing one constant it is 96.8% again, so the sweep was right
    // and the discrepancy was a half-applied change.
    //
    // The two measures disagree on the size of it - 1.6 points on the
    // external samples against 0.2 on the holdout - because they measure
    // different populations: the samples are uniform draws from the allowed
    // box, which is what a quoted door looks like, while the corpus behind the
    // holdout is mostly targeted batches. The samples are the better guide to
    // real use; the holdout is there to confirm the direction, and it does.
    const budget = lineSlack(used.length);

    if (!best || best.bad > budget) {
        return null;
    }

    const out = {
        // Carried so callers can compare competing forms on fit rather than on
        // which was tried first. install.py's line_src never reads it.
        bad: best.bad,
        a: Number(best.a[0].toFixed(5)),
        b: Number(best.b.toFixed(5)),
        lo: vals[0],
        hi: vals[vals.length - 1],
    };

    if (K > 2) {
        out.cuts = best.a.slice(1).map((v) => Number(v.toFixed(5)));
        out.levels = vals;
    }

    return out;
}

// THE BANDS NEED NOT RUN IN BONUS ORDER.
//
// fitLineAnyLevels assigns class 0 to the smallest bonus, class 1 to the next
// and so on, so it can only fit a group whose bonus RISES along the axis. That
// is true of most groups and false of the one that matters most.
//
// 0.2625/0.2253 at two springs carries half of what the model still gets
// wrong, and a fraction walk of it reads, at floors 15 to 23:
//
//   low frac     bonus 0.25
//   middle frac  bonus 0
//   high frac    bonus 1.25
//
// 0.25, then 0, then 1.25 - ordered in frac but not in bonus. The DP could not
// express that, returned a non-zero error, and the group fell through to
// memorising 42 bands. linePredict never cared: it reads lo, mid and hi
// positionally, so the shape was always representable. Only the fitter was
// insisting on an order the reference does not keep.
//
// So each ordering is tried, by relabelling the bonuses to their rank and
// letting the existing fitter work unchanged. Identity goes first, so a group
// that already fits in bonus order is fitted exactly as before. With at most
// three levels there are at most six orderings.
//
// SAFE FOR THE SAME TWO REASONS AS EVER: a line is only returned on a PERFECT
// fit (bad === 0), and the caller still cross-validates it against the bands
// over all the readings and keeps the bands unless the line wins out of
// sample. This widens what can be proposed, not what gets accepted.
function orderings(vals) {
    if (vals.length <= 1) {
        return [vals];
    }

    const out = [];

    for (let i = 0; i < vals.length; i++) {
        const rest = vals.slice(0, i).concat(vals.slice(i + 1));

        for (const tail of orderings(rest)) {
            out.push([vals[i], ...tail]);
        }
    }

    return out;
}

function fitLineAnyOrder(ls, maxLevels) {
    const vals = [...new Set(ls.map((l) => l.bonus))].sort((x, y) => x - y);

    if (vals.length < 2 || vals.length > Math.min(maxLevels, 3)) {
        return fitLineAnyLevels(ls, maxLevels);
    }

    for (const order of orderings(vals)) {
        const rank = new Map(order.map((v, i) => [v, i]));
        const fit = fitLineAnyLevels(
            ls.map((l) => ({ ...l, bonus: rank.get(l.bonus) })), maxLevels
        );

        if (fit) {
            fit.lo = order[0];
            fit.hi = order[order.length - 1];

            if (fit.levels) {
                fit.levels = order;
            }

            return fit;
        }
    }

    return null;
}

// THRESHOLDS THAT DO NOT MOVE TOGETHER.
//
// fitLineAnyLevels searches ONE slope and shares it across every threshold in
// the group - "two parallel thresholds", as the note above it says. That is
// the right default and it is wrong for the group that carries half of what
// the model still gets wrong.
//
// 0.2625/0.2253 at two springs, laid out by the integer part, puts its two
// thresholds on visibly different slopes:
//
//   floor   0.25 -> 0 boundary     0 -> 1.25 boundary
//     15      0.21 .. 0.38            0.71 .. 0.78
//     20      0.45 .. 0.61            0.73 .. 0.79
//     23      0.53 .. 0.72            0.72 .. 0.77
//
// The first climbs about 0.04 per inch of floor; the second sits flat near
// 0.75. Forced parallel, neither can be placed, the fit fails, and the group
// falls through to memorising 42 bands - which is exactly what it was doing.
//
// So each boundary is fitted on its own: K-1 independent binary separations,
// each with its own intercept and slope, and the combined rule is then scored
// as a whole so that boundaries which cross cannot be counted as a fit.
//
// Same two guards as everything else here: the total error has to come inside
// the 3% budget, and the caller still cross-validates the result against the
// bands and keeps the bands unless this predicts better out of sample.
// ONE SLACK FOR BOTH FITTERS. fitLineOwnSlopes had its own copy of the default
// and kept 0.03 when fitLineAnyLevels was re-measured to 0.08, so the fitter
// handling the hardest groups - the ones with non-parallel thresholds - was
// held to a budget less than half the other's.
// 0.12, RE-MEASURED AGAIN after batch R1 added 380 readings sampled within
// 0.03 of a fitted threshold. Those are the hardest readings in the file by
// construction - a reading that close is decided by where the boundary sits to
// three decimals - so they are also the noisiest for a line to absorb, and at
// 0.08 they pushed groups off the line fitter and the band count from 38 to 91.
//
//   LINE_SLACK   bands   clean   within 1"   flagged   five-fold holdout
//      0.08        91    97.9%     99.5%      84.7%        91.9%
//      0.12        38    97.9%     99.3%      85.0%        92.1%
//      0.16        38    97.0%     99.5%      85.3%          -
//      0.20        21    97.4%     99.5%      85.3%          -
//
// AND THEN A FRESH SAMPLE SAID THE TUNING BOUGHT NOTHING.
//
// Every figure above comes from samples this knob had been tuned against,
// which makes them partly in-sample for it. A uniform draw taken afterwards
// (dev/eval-validation-seed61006.json, 380 readings, nothing tuned against it)
// reads the same for every setting:
//
//   slack  support  minside   FRESH   tuned-against   bands
//    0.03    0.03     12      90.3%       97.2%        130
//    0.08    0.06      8      90.3%       98.6%         38
//    0.12    0.06      8      90.3%       98.6%         38
//    0.12    0.03     12      90.9%       98.1%         71
//
// So the 1.4 points these knobs appeared to gain were fitting to those
// samples. 0.12 is kept for the only reason left standing: at the same honest
// accuracy it is 38 bands rather than 130, and fewer memorised parameters is
// the safer thing to carry forward.
//
// The five-fold holdout said 92% throughout while the samples said 98%. The
// holdout was right, and dev/README.md says so at length.
const lineSlack = (n) => Math.floor(n * Number(process.env.LINE_SLACK || 0.18));

function fitThreshold(rows, above) {
    let best = null;

    for (let bi = Number(process.env.BLO || -500); bi <= Number(process.env.BHI || 500); bi += 1) {
        const b = bi / B_STEPS;
        const pts = rows
            .map((r) => ({ u: (r.active - Math.floor(r.active)) - b * Math.floor(r.active), hi: above(r) }))
            .sort((x, y) => x.u - y.u);
        const n = pts.length;

        // A reading is predicted HIGH when u is past the cut. So with the cut
        // below everything, every reading is predicted high and the errors are
        // the LOWS - not the highs, which is what this counted first time and
        // why it fitted nothing: the optimum came out at a slope that drove
        // the threshold negative, predicting one class everywhere.
        //
        //   errors(cut after i) = highs at or before i + lows after i
        let hiBefore = 0;
        let loAfter = pts.filter((p) => !p.hi).length;
        let bad = hiBefore + loAfter;
        let at = -1;

        for (let i = 0; i < n; i++) {
            if (pts[i].hi) hiBefore++; else loAfter--;

            const err = hiBefore + loAfter;

            if (err < bad) { bad = err; at = i; }
        }

        const cut = at < 0 ? pts[0].u - 1e-6
            : at >= n - 1 ? pts[n - 1].u + 1e-6
                : (pts[at].u + pts[at + 1].u) / 2;

        // THE SLOPE IS CHOSEN FOR MARGIN, NOT FLATNESS.
        //
        // For a FIXED slope the cut above is already the best place to put the
        // line: midway between the two readings that straddle it, which is the
        // most room the data allows. But the slope itself was picked by
        // preferring the flattest among equal error counts, which takes no
        // account of how much room that slope leaves. A steeper line can
        // separate the same readings with the gap twice as wide, and it was
        // being passed over.
        //
        // That matters because of where the misses are. Eight of ten land
        // within 0.025 of their own group's threshold and six within 0.007:
        // the rule is right and the boundary is a hair away from the reading
        // that crossed it. Widening the gap the line sits in is the only thing
        // that helps a reading we have never seen, and it costs no parameters.
        //
        // Flatness is kept as the second tie-break, so a slope only wins on
        // margin if it genuinely has more of it.
        // Capped at 1, the width of the range a fraction can occupy - see the
        // longer note in the multi-cut fitter. Past that the line has left the
        // band the readings live in and is separating them by floor instead,
        // which is what splitByCount is for.
        const gap = at < 0 || at >= n - 1
            ? 0
            : Math.min(pts[at + 1].u - pts[at].u, 1);

        const better = !best || bad < best.bad
            || (bad === best.bad && gap > best.gap + 1e-12)
            || (bad === best.bad && Math.abs(gap - best.gap) <= 1e-12
                && Math.abs(b) < Math.abs(best.b));

        if (better) {
            best = { bad, b, a: cut, gap };
        }
    }

    return best;
}

function fitLineOwnSlopes(ls, maxLevels) {
    const vals = [...new Set(ls.map((l) => l.bonus))].sort((x, y) => x - y);

    if (vals.length !== 3 || maxLevels < 2) {
        return null;
    }

    const budget = lineSlack(ls.length);
    let best = null;

    for (const order of orderings(vals)) {
        const rank = new Map(order.map((v, i) => [v, i]));
        const t1 = fitThreshold(ls, (r) => rank.get(r.bonus) >= 1);
        const t2 = fitThreshold(ls, (r) => rank.get(r.bonus) >= 2);

        if (!t1 || !t2) {
            continue;
        }

        // Score the COMBINED rule, so a pair of boundaries that cross over the
        // range of floors in the data cannot be mistaken for a good fit.
        let bad = 0;

        for (const l of ls) {
            const whole = Math.floor(l.active);
            const frac = l.active - whole;
            const first = t1.a + t1.b * whole;
            const second = t2.a + t2.b * whole;
            const got = frac > second ? order[2] : frac > first ? order[1] : order[0];

            if (Math.abs(got - l.bonus) > 1e-9) {
                bad++;
            }
        }

        // ORDERING IS NOT CHOSEN FOR MARGIN, measured and reverted.
        //
        // The two thresholds here come from fitThreshold, which maximises its own
        // margin, so the only thing still decided by first-wins is WHICH order of
        // the three bonus values to fit. Preferring the ordering whose tighter cut
        // has more room changed 13 rungs' tables and not one scored reading:
        // 6998/7728 either way on the fixed-population holdout. Rewriting a
        // quarter of the table for no measured effect is churn, so the tie stays
        // with the first ordering listed.
        if (!best || bad < best.bad) {
            best = {
                bad,
                a: Number(t1.a.toFixed(5)), b: Number(t1.b.toFixed(5)),
                a2: Number(t2.a.toFixed(5)), b2: Number(t2.b.toFixed(5)),
                lo: order[0], mid: order[1], hi: order[2],
            };
        }
    }

    if (!best || best.bad > budget) {
        return null;
    }

    return best;
}

const unbounded = [];
const crossValidated = [];

function pickK(g) {
    const fromCycles = g.Ks.length ? Number(median(g.Ks).toFixed(1)) : null;
    const b = switchBounds.get(g.outer + "/" + g.inner);

    // NO SWITCH BOUNDS. K then comes from the cycle-count median alone, which
    // is the weakest way to get it - inverting a rounded cycle count is good
    // to about 1%, against 0.15% from a switch point.
    //
    // This used to be silent, and that silence cost a batch: the stiff end of
    // the ladder was swept in 25 lb steps, boundsFromSwitches only accepts a
    // switch pair within 6 lb, so every rung above 1700 lb got no bounds at
    // all and fell back here. Thirteen wire misses, with nothing in the output
    // to say why. Rungs that land here are now named.
    if (!b || !b.lo.length || !b.hi.length) {
        unbounded.push(`${g.outer}/${g.inner} (n=${g.Ks.length})`);

        return fromCycles;
    }

    const lo = Math.max(...b.lo);
    const hi = Math.min(...b.hi);

    // CONTRADICTORY BOUNDS. Each reading says K must clear its own switch
    // point and stay under the next one up, so lo > hi means two readings on
    // this rung cannot both be satisfied - our cycle law is slightly wrong
    // here, not the data.
    //
    // This used to fall through to the cycle-count median, silently. On
    // 0.3625/0.283 that median sits 0.18% above the old feasible midpoint,
    // and that 0.18% was enough to stop the ladder one rung early on EIGHT
    // readings - they got 0.3625/0.283 where the reference gives
    // 0.3625/0.289. A K chosen by a rule that ignores the switch points has
    // no reason to land anywhere useful.
    //
    // So pick the candidate that violates the fewest constraints, breaking
    // ties on the smallest total relative violation. That is the most
    // readings this rung can satisfy at once, and it degrades gracefully
    // instead of jumping.
    if (!(hi > lo)) {
        const candidates = [...new Set([...b.lo, ...b.hi,
            ...(fromCycles === null ? [] : [fromCycles])])];
        let best = null;

        for (const k of candidates) {
            let violated = 0;
            let amount = 0;

            for (const x of b.lo) {
                if (k < x) { violated += 1; amount += (x - k) / x; }
            }

            for (const x of b.hi) {
                if (k > x) { violated += 1; amount += (k - x) / x; }
            }

            if (!best || violated < best.violated ||
                (violated === best.violated && amount < best.amount)) {
                best = { k, violated, amount };
            }
        }

        if (process.env.DUMP_K) {
            const loAt = b.loSrc?.[b.lo.indexOf(lo)] ?? "?";
            const hiAt = b.hiSrc?.[b.hi.indexOf(hi)] ?? "?";
            console.error(`    lo ${lo.toFixed(1)} set by: ${loAt}`);
            console.error(`    hi ${hi.toFixed(1)} set by: ${hiAt}`);
            const sorted = b.hi.map((v, n) => [v, b.hiSrc[n]]).sort((x, y) => x[0] - y[0]);
            console.error("    all hi bounds, lowest first:");
            for (const [v, who] of sorted.slice(0, 6)) {
                console.error(`      ${v.toFixed(1).padStart(9)}  ${who}`);
            }
            console.error(
                `  ${(g.outer + "/" + g.inner).padEnd(16)} CONTRADICTORY: lo ${lo.toFixed(1)} > hi ${hi.toFixed(1)}` +
                `  cycles ${fromCycles}  -> K ${best.k.toFixed(1)}` +
                ` (violates ${best.violated} of ${b.lo.length + b.hi.length})`
            );
        }

        return Number(best.k.toFixed(1));
    }

    if (process.env.DUMP_K) {
        console.error(
            `  ${(g.outer + "/" + g.inner).padEnd(16)} lo ${lo.toFixed(1).padStart(9)} ` +
            `hi ${hi.toFixed(1).padStart(9)}  width ${((hi - lo) / lo * 100).toFixed(2)}%` +
            `  cycles ${fromCycles}` +
            `  ${fromCycles !== null && fromCycles >= lo && fromCycles <= hi ? "(cycles used)" : "(midpoint used)"}`
        );
    }

    if (fromCycles !== null && fromCycles >= lo && fromCycles <= hi) {
        return fromCycles;
    }

    return Number(((lo + hi) / 2).toFixed(1));
}

const out = [...rungs.values()]
    // A rung with a zero wire size is a malformed reading, not a rung. It
    // carried K null so install.py skipped it, but it had no business being
    // here and it made the table unreadable.
    .filter((g) => g.outer > 0 && g.inner > 0)
    .map((g) => {
        const S = 2 * (divider(g.inner, 3.75) + divider(g.outer, 6));
        const byCount = {};

        for (const sp of [1, 2, 3, 4]) {
            const ls = g.lens.filter((l) => l.springs === sp && l.ok);

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
            // A line where it earns it. For a two-level group the line is
            // strictly simpler than any band arrangement and is taken on
            // sight; for a three-level group it is a real structural claim
            // and has to beat the bands on readings neither has seen.
            let line = needed ? fitLine(ls) : null;

            // The family that produced the line has to be the family the
            // cross-validation refits with. It was always fitLine, so a line
            // from fitLineOwnSlopes was scored by refitting with the
            // shared-slope fitter - which fails on every fold, scores zero,
            // and hands the group back to the bands however good the line
            // was. That is why 0.2625/0.2253 at two springs kept its 42
            // bands after the independent-slope fitter went in.
            let lineFitter = fitLine;

            // The shared-slope line could not be placed. Before falling back
            // to a band table, try letting the thresholds move independently.
            if (!line && needed) {
                line = fitLineOwnSlopes(ls, LINE_LEVELS);

                if (line) {
                    lineFitter = (train) => fitLineOwnSlopes(train, LINE_LEVELS);
                }
            }

            if (line && line.mid !== undefined) {
                const lineCv = cvScore(ls, lineFitter, linePredict);
                const bandCv = cvScore(ls, (t) => bands(t).bands, bandPredict);

                if (!(lineCv > bandCv)) {
                    crossValidated.push(
                        `${g.outer}/${g.inner} at ${sp} spring(s): two thresholds ` +
                        `${(lineCv * 100).toFixed(1)}% vs bands ${(bandCv * 100).toFixed(1)}% ` +
                        `out of sample over ${ls.length} readings - kept the bands`
                    );
                    line = null;
                }
            }

            // NO_OVERRIDES measures the stiffness correction on its own, with
            // no bands, lines or splits layered on top of it.
            if (process.env.NO_OVERRIDES) {
                continue;
            }

            const split = line ? null : (needed ? fitSplit(ls) : null);

            if (line) {
                byCount[sp] = { line, n: ls.length };
            } else if (split) {
                byCount[sp] = { split, n: ls.length };
            } else if (needed && b.bands.length <= MAX_BANDS) {
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
            sMult: g.sMult ?? 1,
            twoOffset: g.twoOffset ?? 0,
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
        // Each spring count may carry bands, a line or a regime split. This
        // assumed bands and threw, which killed the whole printer - and the
        // overfit and contradiction reports print AFTER it, so they silently
        // stopped running the moment lines were introduced. "0 rungs where
        // frac alone provably fails" was a crashed report, not a clean bill.
        const bc = Object.entries(r.byCount)
            .map(([sp, v]) => {
                if (v.split) {
                    return `${sp}spr:split@${v.split.from}/n${v.n}`;
                }

                if (v.line) {
                    const k = v.line.levels ? v.line.levels.length : 2;

                    return `${sp}spr:line${k}L/n${v.n}`;
                }

                return `${sp}spr:${v.bands.length}b/n${v.n}`;
            })
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

    if (crossValidated.length) {
        console.log("\n  GROUPS WHERE THE TWO-THRESHOLD LINE LOST ITS OWN CROSS-VALIDATION:");

        for (const c of crossValidated) {
            console.log("    " + c);
        }
    }

    if (unbounded.length) {
        console.log("\n  RUNGS WITH NO SWITCH POINT - K from the cycle median only (~1% vs ~0.15%):");
        console.log("  (sweep either side of where these switch, in steps of 6 lb or less)");

        for (const u of unbounded) {
            console.log("    " + u);
        }
    }

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
