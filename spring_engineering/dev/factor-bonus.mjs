// IS THE BONUS TWO DECISIONS WEARING ONE LABEL?
//
//   node dev/factor-bonus.mjs
//
// WHERE THIS CAME FROM. Scored out of sample by the form the fitter chose,
// the groups that could not fit a line are the worst population left - split
// groups at 87.03% against 94.69% for lines - and ALL TEN of them are at two
// springs. `BORROW_REPORT` in `derive.mjs` then found why, and the reason is
// structural:
//
//   0.295/0.2437   1spr  levels {0, 1}
//                  2spr  levels {0, 0.25, 1, 1.25}    <- both sets at once
//                  3spr  levels {0.25, 1.25}
//                  4spr  levels {0.25, 1.25}
//
// which is `duplexSnapToGrid` lifting whole inches to the quarter above at 3+
// springs and not at 2. So two springs is the only count where the quarter is
// LIVE, and the four levels factor exactly:
//
//     bonus  =  step        +  quarter
//               (0 or 1)       (0 or 0.25)
//
// THE HYPOTHESIS. The fitter has to express four levels with thresholds in
// one dimension, which forces a three-level line or a split on the floor.
// If `step` and `quarter` are each separately predictable, they are two
// TWO-LEVEL problems, each with every reading in the group rather than a
// quarter of them - which is the same argument that made pooling work.
//
// WHAT THIS TOOL DOES AND DELIBERATELY DOES NOT DO. It measures the PREMISE
// and changes nothing. For each 2-spring group it fits the best single
// threshold `frac > a + b*floor` for each decision on its own, both in sample
// and five-fold cross-validated, and prints what the product of the two would
// score against what the installed form actually scores.
//
// READ THE CV COLUMN, NOT THE IN-SAMPLE ONE. A threshold fitted and scored on
// the same readings is an upper bound and nothing more; this project has twice
// read one as a finding.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load, make } from "./harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const mod = await load();
const corpus = JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8"));

// Gather the readings the way derive.mjs sees them: the active length, its
// floor and fraction, and the bonus the reference implies.
const groups = new Map();

for (const r of corpus.readings) {
    if (r.expect?.duplexInnerLength === undefined) continue;
    if ((r.state.springs ?? 2) !== 2) continue;          // the live count

    let c;

    try {
        c = make(mod, r.state);
    } catch {
        continue;
    }

    const step = c.duplexStep;

    if (!step) continue;

    // Only where the WIRE already agrees - otherwise the bonus describes a
    // different spring, which is the mistake recorded against the first cycle
    // comparison.
    if (`${step.outerWire}/${step.innerWire}`
        !== `${parseFloat(r.expect.duplexOuterWire)}/${parseFloat(r.expect.duplexInnerWire)}`) {
        continue;
    }

    const active = c.duplexActiveLength;

    if (!(active > 0)) continue;

    const floor = Math.floor(active);
    const bonus = Number((r.expect.duplexInnerLength - floor).toFixed(2));

    // THE FACTORISATION. Only the four combinations the structure predicts
    // count; anything else (a -1, a 7) is an outlier for this question and is
    // counted separately rather than silently folded in.
    const quarter = Math.abs(bonus - Math.round(bonus * 4) / 4) < 1e-9
        && Math.abs((bonus * 4) % 1) < 1e-9
        ? Number((bonus - Math.floor(bonus)).toFixed(2)) : null;
    const whole = Math.floor(bonus);
    const inFamily = (whole === 0 || whole === 1) && (quarter === 0 || quarter === 0.25);

    const key = `${step.outerWire}/${step.innerWire}`;

    if (!groups.has(key)) groups.set(key, []);

    groups.get(key).push({
        floor, frac: active - floor, bonus,
        step: whole, quarter, inFamily,
    });
}

// One threshold, `frac > a + b*floor`, fitted by the same kind of grid scan
// derive.mjs uses. Returns the rule and its in-sample hit count.
function fitThreshold(rows, label) {
    let best = null;

    for (let bi = -250; bi <= 250; bi += 1) {
        const b = bi / 2000;
        const pts = rows.map((r) => ({ u: r.frac - b * r.floor, y: label(r) }))
            .sort((x, y) => x.u - y.u);
        // Every cut position; the answer above the cut is whichever class is
        // commoner there, so both polarities are covered.
        for (let i = 0; i <= pts.length; i++) {
            const below = pts.slice(0, i), above = pts.slice(i);

            for (const hiVal of [true, false]) {
                const ok = below.filter((p) => p.y === !hiVal).length
                    + above.filter((p) => p.y === hiVal).length;

                if (!best || ok > best.ok) {
                    best = {
                        ok, b, hiVal,
                        a: i === 0 ? pts[0].u - 1e-6
                            : i === pts.length ? pts[pts.length - 1].u + 1e-6
                                : (pts[i - 1].u + pts[i].u) / 2,
                    };
                }
            }
        }
    }

    return best;
}

const apply = (rule, r) => (r.frac - rule.b * r.floor > rule.a ? rule.hiVal : !rule.hiVal);

// Five-fold, so the figure is not the fit scoring itself.
function cv(rows, label) {
    let right = 0, total = 0;

    for (let k = 0; k < 5; k++) {
        const train = rows.filter((_, i) => i % 5 !== k);
        const test = rows.filter((_, i) => i % 5 === k);

        if (!train.length || !test.length) continue;

        const rule = fitThreshold(train, label);

        for (const r of test) {
            total += 1;
            right += apply(rule, r) === label(r) ? 1 : 0;
        }
    }

    return total ? right / total : -1;
}

// Both decisions together, scored as ONE prediction - which is what the
// length actually needs. A reading only counts if step AND quarter are right.
function cvBoth(rows) {
    let right = 0, total = 0;

    for (let k = 0; k < 5; k++) {
        const train = rows.filter((_, i) => i % 5 !== k);
        const test = rows.filter((_, i) => i % 5 === k);

        if (!train.length || !test.length) continue;

        const sRule = fitThreshold(train, (r) => r.step === 1);
        const qRule = fitThreshold(train, (r) => r.quarter === 0.25);

        for (const r of test) {
            total += 1;
            right += (apply(sRule, r) === (r.step === 1)
                && apply(qRule, r) === (r.quarter === 0.25)) ? 1 : 0;
        }
    }

    return total ? right / total : -1;
}

const pct = (x) => (x < 0 ? "   -  " : `${(100 * x).toFixed(1)}%`.padStart(6));

console.log("=".repeat(86));
console.log("THE BONUS AS TWO DECISIONS - two-spring groups, wire already right");
console.log("=".repeat(86));
console.log("  rung              n  outside   step cv   quarter cv   BOTH cv   product");

const totals = { n: 0, both: 0 };

for (const [rung, all] of [...groups].sort((a, b) => b[1].length - a[1].length)) {
    if (all.length < 25) continue;

    const rows = all.filter((r) => r.inFamily);
    const outside = all.length - rows.length;

    if (rows.length < 25) continue;

    const s = cv(rows, (r) => r.step === 1);
    const q = cv(rows, (r) => r.quarter === 0.25);
    const both = cvBoth(rows);

    totals.n += rows.length;
    totals.both += both * rows.length;

    console.log(`  ${rung.padEnd(16)}${String(rows.length).padStart(4)}`
        + `${String(outside).padStart(8)}   ${pct(s)}      ${pct(q)}    ${pct(both)}`
        + `    ${pct(s * q)}`);
}

console.log("-".repeat(86));
console.log(`  pooled over ${totals.n} readings: BOTH cv ${pct(totals.both / totals.n)}`);
console.log();
console.log("  COMPARE AGAINST 87.03%, which is what the split groups score out of");
console.log("  sample today (dev/derive.mjs BORROW_REPORT note). `outside` counts");
console.log("  readings whose bonus is not step+quarter at all - those are lost by");
console.log("  this form however well the two thresholds do, so a fair comparison");
console.log("  multiplies BOTH cv by n/(n+outside).");
