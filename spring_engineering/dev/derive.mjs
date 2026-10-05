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

        readings.push({
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

    // rawActive is the formula's own value. The per-rung stiffness correction
    // is fitted after every rung is gathered, and `active` is then rewritten,
    // so the bands below fit whatever is LEFT rather than re-absorbing an
    // error the stiffness already explains.
    // The rounded TIPPT, matching duplexActiveLength: the reference computes
    // from the figure it displays, as it does for cycles and MIP.
    const shownTippt = Math.round(c.tipptExact * 10) / 10;
    const rawActive =
        springs * (divider(r.inner, 3.75) + divider(r.outer, 6)) / shownTippt;

    g.lens.push({
        springs, rawActive, length: r.length,
        active: rawActive,
        frac: rawActive - Math.floor(rawActive),
        bonus: Number((r.length - Math.floor(rawActive)).toFixed(2)),
    });
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

    g.sMult = 1;

    if (usable.length >= 12) {
        const fit = fitStiffness(usable);

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
        const second = line.a2 + line.b * whole;

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

    const floors = [...new Set(ls.map((l) => Math.floor(l.active)))]
        .sort((x, y) => x - y);
    const viable = [];

    for (const from of floors) {
        const below = ls.filter((l) => Math.floor(l.active) < from);
        const above = ls.filter((l) => Math.floor(l.active) >= from);

        if (below.length < 12 || above.length < 12) {
            continue;
        }

        const b = fitLineAnyLevels(below, 2);
        const a = fitLineAnyLevels(above, 2);

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
                const b = fitLineAnyLevels(
                    train.filter((l) => Math.floor(l.active) < cand.from), 2
                );
                const a = fitLineAnyLevels(
                    train.filter((l) => Math.floor(l.active) >= cand.from), 2
                );

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
const LINE_LEVELS = Number(process.env.LINE_LEVELS || 2);

function fitLine(ls) {
    return fitLineAnyLevels(ls, LINE_LEVELS);
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

    const floor = Math.max(2, Math.ceil(ls.length * 0.03));
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
        const b = bi / 2000;
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

        // Among equally good slopes prefer the flattest, which claims least
        // off the end of the data where these lines are actually used.
        if (best && (bad > best.bad ||
            (bad === best.bad && Math.abs(b) >= Math.abs(best.b)))) {
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

        best = { bad, b, a: cuts.map(cutAt) };
    }

    if (!best || best.bad !== 0) {
        return null;
    }

    const out = {
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

            if (line && line.mid !== undefined) {
                const lineCv = cvScore(ls, fitLine, linePredict);
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
