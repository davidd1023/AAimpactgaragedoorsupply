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
// different answer. What separates them is the integer part, and the
// threshold moves with it - on that rung the bonus flips at about 0.80 at
// floor 17, 0.84 at floor 18, 0.91 at floor 24 and never by floor 25.
//
// Fitting t = a + b*floor instead explains 39 of the 41 two-bonus groups with
// ONE line each. That is two numbers where the fitter previously wanted up to
// twenty-two alternating bands - 0.375/0.295 at one spring needed EIGHTEEN,
// which fit its readings and predicted nothing. Two parameters over fifteen
// buckets cannot do that.
//
// Returns null unless exactly two bonus values appear and some line satisfies
// every reading; a group with three or more keeps its bands.
function fitLine(ls) {
    const vals = [...new Set(ls.map((l) => l.bonus))].sort((x, y) => x - y);

    if (vals.length !== 2) {
        return null;
    }

    const [lo, hi] = vals;
    const pts = ls.map((l) => ({
        F: Math.floor(l.active),
        t: l.active - Math.floor(l.active),
        high: l.bonus === hi,
    }));

    let best = null;

    for (let b = -0.03; b <= 0.09; b += 0.0005) {
        for (let a = -2; a <= 2; a += 0.0025) {
            let bad = 0;

            for (const pt of pts) {
                const thr = a + b * pt.F;

                // At or below the threshold takes the low bonus, above it the
                // high one. Mirrors duplexLength exactly.
                if (pt.high ? pt.t <= thr : pt.t > thr) {
                    bad += 1;

                    if (best && bad >= best.bad) {
                        break;
                    }
                }
            }

            if (!best || bad < best.bad) {
                best = { a: Number(a.toFixed(4)), b: Number(b.toFixed(5)), bad };
            }

            if (best.bad === 0) {
                break;
            }
        }

        if (best && best.bad === 0) {
            break;
        }
    }

    return best && best.bad === 0 ? { a: best.a, b: best.b, lo, hi } : null;
}

const unbounded = [];

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
            // A line first - it is two parameters and it explains the frac
            // collisions that no band arrangement can.
            const line = needed ? fitLine(ls) : null;

            if (line) {
                byCount[sp] = { line, n: ls.length };
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
