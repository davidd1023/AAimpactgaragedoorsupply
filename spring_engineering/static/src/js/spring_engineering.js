/** @odoo-module **/

import { Component, onWillStart, useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// --- Spring length constants ---------------------------------------------
// Verified exactly (to the cent) against 11 reference results from the
// manufacturer's calculator: 2 drums, spring IDs 1 13/16"-6", wire
// 0.125"-0.4218", and a 150-500 lb weight sweep.
//
// TORSION_CONSTANT: the standard torsion-spring rate denominator. The
// theoretical value from beam mechanics is 2*pi*64/(4*pi) = 10.186; 10.2 is
// the value in use. The 10.8 previously here is a different published
// convention and does not match this manufacturer.
//
// End allowance is counted in WIRE DIAMETERS, not inches. The old hard-coded
// 1.25" and 0.75" are exactly 5 x 0.25" and 3 x 0.25", i.e. the right coil
// counts frozen at one wire size - correct for 0.25" wire and wrong for every
// other size.
const TORSION_CONSTANT = 10.2;
const END_COILS_SMALL_ID = 5;   // spring ID <= 4.5"
const END_COILS_LARGE_ID = 3;   // spring ID  > 4.5"
const LARGE_ID_THRESHOLD = 4.5;

// --- Cycle life ----------------------------------------------------------
// cycles = (CYCLE_COEFFICIENT * wire^CYCLE_WIRE_EXPONENT / torque) ^ CYCLE_EXPONENT
// where torque is the load carried by ONE spring at full wind (in-lb).
//
// Reverse-engineered from 13 reference results and accurate to 0.025% over a
// range of 494 to 320,090 cycles. Established by the data:
//   * spring ID has NO effect at all (an ID sweep at fixed wire/torque returned
//     an identical cycle count), so there is no spring-index / Wahl term;
//   * a weight sweep and a wire sweep are both exact power laws in stress, but
//     with DIFFERENT slopes (-4.670 vs -4.343). Stress alone therefore cannot
//     be the driver. The gap resolves to an extra wire^0.21 term, i.e. tensile
//     strength falling with wire diameter, as in the ASTM spring-wire grades.
// Equivalent stress form: cycles = (1265142 / (S * wire^0.21))^4.67,
// with S = 32*torque/(pi*wire^3).
// Calibration of the effective drum radius, for HI-LIFT DRUMS ONLY.
//
// rEff and CYCLE_COEFFICIENT are DEGENERATE: scaling both by the same factor
// leaves every cycle count identical, because cycles depend only on their
// ratio. Cycle counts fix the ratio, never the absolute radius - so a radius
// derived from cycle counts inherits whatever scale the coefficient had.
//
// A displayed multiplier times a displayed turns count gives rEff with no
// cycle law involved, and on the hi-lift drums those products sit consistently
// BELOW the radii derived from cycles. The manufacturer's catalog agrees: it
// prints 2.719 for D525-54 where cycles imply 2.71942.
//
// This is NOT a global miscalibration, which was checked and ruled out. The
// windows of scale factors that reproduce every reported turns row are
//     525-54HL          [0.9998215, 0.9998448]
//     D400-96 standard  [0.9999303, 1.0008714]
// and they do not intersect. One factor cannot serve both.
//
// The split has a cause. CYCLE_COEFFICIENT above is documented as accurate
// over 494 to 320,090 cycles. The hi-lift radii were pinned from 100 lb cycle
// counts as high as 959,433 - outside that range, where the law drifts - while
// the standard drums were pinned from counts inside it. So the bias belongs to
// the hi-lift family, and scoping the correction to that family is the correct
// scope rather than a patch.
//
// Applied together with a matching scale on the cycle coefficient, so hi-lift
// cycle counts are unchanged; only their displayed turns move, by 0.0167%.
// Standard drums are untouched in every respect.
//
// The 575-120 wants a slightly different window ([0.9994499, 0.9997869]), but
// that window is computed through its own multiplier surface, which still
// carries the catalog's 0.03% error - so it reflects that error, not a real
// disagreement. The value here is taken from the 525, whose multipliers are
// good to 1e-6. The two should reconcile once the 575 is fitted to the
// calculator directly.
const HILIFT_RADIUS_SCALE = 0.9998332;

const CYCLE_COEFFICIENT = 124205;
const CYCLE_WIRE_EXPONENT = 2.79;
const CYCLE_EXPONENT = 4.67;

// --- Spring weight --------------------------------------------------------
// The steel weight of ONE spring: wire cross-section * wire length * density.
//
//   coils      = springLength / wire          (closed-wound body)
//   wireLength = pi * (springID + wire) * coils
//   volume     = (pi/4) * wire^2 * wireLength
//   weight     = STEEL_DENSITY * volume
//              = STEEL_DENSITY * (pi^2/4) * wire * (springID + wire) * length
//
// Derived, not fitted. Solving for the density each reference result implies
// (12.00 / 12.18 / 12.30 lb) gives the window 0.283484-0.283672 lb/in^3, and
// 0.2836 - the textbook density of spring steel - falls inside it and
// reproduces all three to the cent. Because the constant is a real material
// property rather than a tuned coefficient, this should hold for any spring
// ID, wire size and length, not just near those three points.
//
// Per SPRING, not per set: springLength is the length of each individual
// spring (it scales with the spring count, since each spring in a set of n
// carries IPPT/n and so is softer and longer).
const STEEL_DENSITY = 0.2836;   // lb/in^3

// --- Drum table -----------------------------------------------------------
// Each drum carries:
//
//   rEff        Effective drum radius in inches, = multiplier * turns. Peak
//               torque at full wind is weight * rEff, so rEff belongs to the
//               DRUM ALONE and does not change with door height. Pinned per
//               drum from 3 reference cycle counts (20/300/1000 lb over
//               0.125"-0.625" wire, 12.5k to 7.2M cycles), whose solution
//               windows overlap in a band under 1e-6 wide.
//
//   turnsCurve  Coefficients of the turns-vs-height formula below. Turns and
//               the multiplier are COMPUTED from door height, not looked up
//               per foot, so any height works - inches included.
//
// Why rEff is height-independent: on all three drums a measured 4-10 ft sweep
// holds multiplier * turns constant (2.2754 / 2.2934 / 2.9365; the ~0.14%
// spread is only the 2-decimal rounding of the reference turns). Physically
// that is static balance at full wind - the spring holds weight * drum radius
// and the door height does not enter. So raising the door LOWERS the multiplier
// and RAISES the turns, leaving peak torque, and therefore the CYCLE COUNT,
// unchanged. Only TIPPT and spring length move with height.
// rEff IS THE DRUM'S MOMENT ARM. These were fitted, and the reference's own
// drum record confirms what they are:
// GET /spring-engineering/drum?drumName=... returns highMomentArm, and it
// agrees with every fitted value to the precision it publishes -
//
//   D400-96    fitted 2.2753521   record 2.275
//   D400-144   fitted 2.2933549   record 2.293
//   D525-216   fitted 2.9364545   record 2.936
//
// so these are geometry, not curve-fitting artefacts. The fitted figures are
// kept because they carry four more digits than the record publishes.
//
// turnsCurve is NOT in the record and cannot be derived from it. The record's
// `circumference` gives turns to about a tenth of a turn - turns is roughly
// height/circumference plus one, the extra turn being the spiral first wrap -
// and a tenth of a turn is a 1% multiplier error where this file holds 2e-5.
// Good enough to offer an unmeasured drum with a warning; not good enough to
// match the reference.
const DRUMS = {
    "CANIMEX/TF D400-144": {
        rEff: 2.2933549,
        turnsCurve: {
            a: 0.918018474,
            b: 1.224217309,
            c: 0.903742416,
            d: 6.136653231,
            e: -11.978871764,
            f: 24.691717891,
        },
    },
    "CANIMEX/TF D400-96": {
        rEff: 2.2753521,
        turnsCurve: {
            a: 0.926270103,
            b: 1.182458766,
            c: 1.622498182,
            d: 1.457531341,
            e: 3.164283001,
            f: 5.912155063,
        },
    },
    "CANIMEX/TF D525-216": {
        rEff: 2.9364545,
        turnsCurve: {
            a: 0.702285693,
            b: 0.936356104,
            c: 0.999506286,
            d: 3.138832124,
            e: -3.937059973,
            f: 13.452757892,
        },
    },
};

// Turns at full wind for a door of `heightFeet` (fractional - inches go in as
// inches/12):
//
//     turns = a*H + b + c/H + d/H^2 + e/H^3 + f/H^4
//
// Fitted per drum against 22 reference multipliers in total: a 4-10 ft
// whole-foot sweep for each drum, plus 7'6" on D400-96. That off-grid point
// started as a PREDICTION (0.271486) which the reference calculator then
// confirmed exactly, so the curve is checked between the feet, not only on
// them. Worst error over all 22 points is 2.3e-7, i.e. every reference
// multiplier reproduces to the full 6 displayed decimals.
//
// A straight line misses by 1.33%, so the curvature is real, and the inverse
// powers are what buy the last decimals - dropping 1/H^3 costs 1e-5, which
// shows in the 5th decimal of the displayed multiplier.
//
// This is an empirical fit, not a derived law: no drum geometry reproduces it
// (a constant-radius drum makes turns linear in height, which this is not; a
// linear taper misses by 5.5%). Trust it across the measured 4-10 ft band and
// a little beyond; it stays smooth and monotonic out to 16 ft, but a new drum
// needs its own sweep rather than borrowing another drum's coefficients.
const CURVE_MIN_FEET = 3;

function drumTurns(drum, heightFeet) {
    if (!drum.turnsCurve) {
        return 0;
    }

    // Far below the measured band the inverse-power terms take over and the
    // curve stops being monotonic (turns would start RISING as the door gets
    // shorter), so clamp short of that. No real door is this low.
    const height = Math.max(Number(heightFeet) || 0, CURVE_MIN_FEET);

    const { a, b, c, d, e, f } = drum.turnsCurve;

    return (
        a * height +
        b +
        c / height +
        d / height ** 2 +
        e / height ** 3 +
        f / height ** 4
    );
}

// Hi-lift below a full 12" is frozen to 0" by the reference calculator.
// Confirmed on the 525-54HL, where 6", 8", 9", 10" and 11" all return
// bit-identical output, and on the 575-120, where 7'0"/6" returns the
// 7'0"/0" value. Shared by both hi-lift drum families.
const HILIFT_MIN = 12;

// --- CANIMEX/TF 575-120 ---------------------------------------------------
// Height curves fitted DIRECTLY to the reference calculator, one per measured
// hi-lift column. The catalog is no longer part of the arithmetic for this
// drum: it prints 4 decimals, and that rounding was the floor the previous
// base-plus-correction build kept hitting. These come from 116 six-decimal
// reference multipliers and reproduce every one of them exactly.
//
// The spiral is the drum's own, recovered from its 100 lb cycle counts. Its
// pitch of 0.313097" is the same constant the 525-54HL and D800-120 use, to
// seven figures - the calculator applies one pitch across hi-lift drums.
// The hi-lift spiral constants are the record's geometry too:
// spiralA is flatMomentArm squared and spiralB is rateOfRise/pi.
//
//   575-120    A 8.8176917   record 2.969^2 = 8.814961
//   525-54HL   A 7.3952515   record 2.719^2 = 7.392961
//   D800-120   A 17.015618   record 4.125^2 = 17.015625  (seven figures)
//   all        B ~0.09966    record 0.313/pi = 0.0996310
//
// HL800_A below is deliberately 17.0209238 rather than the record's 17.015625:
// the record publishes the catalogue nominal and the calculator behaves like
// r0 = 4.1256. HL800_NODE_A carries the catalogue value, which is why there are
// two. Measuring the calculator beat reading the catalogue, and both are kept.
const HL575_A = 8.8176917;         // r0^2, r0 = 2.96946"
const HL575_B = 0.099661791;       // pitch/pi, pitch = 0.313097"
const HL575_MIN = 12;
const HL575_MAX = 120;

// [hiLift, a, b, c, d, e, f, g] for
//     multiplier = a*(H/10) + b + c*(10/H) + d*(10/H)^2 + e*(10/H)^3
//                  + f*(10/H)^4 + g*(10/H)^5
// the standard drums' six-term family plus an optional seventh. The seventh
// is only needed by columns reaching past about 20 ft - without it they sit
// at 1.1e-06 instead of 4e-07 - so it is chosen per column by leave-one-out
// and left at zero where six terms do better. H/10 and 10/H only keep the
// basis conditioned across the span.
//
// Between columns the coefficients are interpolated with a local cubic in
// rEff, the drum's own coordinate.
//
// 190 six-decimal reference multipliers, 15 hi-lift columns, door heights
// from 6 to 32 ft. 186 of the 190 reproduce exactly; four miss in the
// seventh decimal.
//
// WHAT IS STILL LOOSE. Within a column, predicting a withheld height lands
// at 1e-06 to 6e-06. BETWEEN columns it is 2.1e-04 at worst and 4.3e-05
// median, concentrated on the lowest row of each column where the
// multiplier collapses. Adding the 18", 66" and 78" columns halved it from
// 5.5e-04, and the pattern holds that closer column spacing helps rather
// than more heights: columns at 6", 30", 42" and 54" are the next step.
const HL575_COLUMNS = [
        [  0,  -0.0000060557,   0.0000390956,   0.4613358759,  -0.0344926349,  -0.0000659246,   0.0000144417,   0.0000000000],
        [ 12,   0.0000041957,   0.0000041460,   0.4916691235,  -0.0790692597,  -0.0003242280,   0.0000155106,   0.0000000000],
        [ 18,  -0.0000416799,   0.0002979434,   0.5053590803,  -0.0990953336,  -0.0016132647,   0.0003524751,  -0.0000562322],
        [ 24,  -0.0014256751,   0.0080764309,   0.5015392858,  -0.0978885289,  -0.0167155303,   0.0053504287,  -0.0007733789],
        [ 36,   0.0000546232,  -0.0004115481,   0.5485383893,  -0.1608589044,  -0.0025891039,  -0.0007149759,   0.0000978079],
        [ 48,  -0.0000023606,   0.0000037512,   0.5731257401,  -0.1945130659,  -0.0082484460,  -0.0004512108,   0.0000000000],
        [ 60,   0.0000656664,  -0.0004553287,   0.5990170812,  -0.2285674349,  -0.0132887300,  -0.0014333021,   0.0000000000],
        [ 66,   0.0000613650,  -0.0004978692,   0.6112944345,  -0.2444038525,  -0.0163756071,  -0.0022344814,   0.0000000000],
        [ 72,   0.0002936128,  -0.0019029394,   0.6263998974,  -0.2629054733,  -0.0180405697,  -0.0036659793,   0.0000000000],
        [ 78,  -0.0000355262,   0.0003061307,   0.6318796070,  -0.2679906058,  -0.0296067749,  -0.0016031413,  -0.0006357620],
        [ 84,  -0.0002480766,   0.0016174980,   0.6399158368,  -0.2766992129,  -0.0380200869,  -0.0012482515,  -0.0010947119],
        [ 90,   0.0004246081,  -0.0031397231,   0.6648343444,  -0.3100484548,  -0.0259414803,  -0.0102532141,   0.0000000000],
        [ 96,  -0.0000317925,   0.0003606592,   0.6646483482,  -0.3029092141,  -0.0498332864,  -0.0026619689,  -0.0023315713],
        [108,  -0.0000388435,   0.0004665227,   0.6853128621,  -0.3218906285,  -0.0671630412,  -0.0028639628,  -0.0048478981],
        [120,  -0.0001238582,   0.0014822503,   0.7010986174,  -0.3280035357,  -0.0995926207,   0.0054551090,  -0.0111930374],
];

// Below 12" and above the maximum both fall back to the 0" row - above the
// maximum it is a fallback, not a clamp. Measured at 125", which returns the
// 0" cycle count of 3762 rather than the 120" one, and the D800-120 behaves
// the same way.
function hl575Applied(hiLiftInches) {
    const hl = Number(hiLiftInches) || 0;

    if (hl < HL575_MIN || hl > HL575_MAX) {
        return 0;
    }

    return hl;
}

function hl575REff(hiLiftInches) {
    return Math.sqrt(HL575_A + HL575_B * hl575Applied(hiLiftInches));
}

function hl575ColumnREff(hiLift) {
    return Math.sqrt(HL575_A + HL575_B * hiLift);
}

function hl575Multiplier(heightFeet, hiLiftInches) {
    const height = Number(heightFeet) || 0;

    if (height <= 0) {
        return 0;
    }

    const u = hl575REff(hiLiftInches);

    let nearest = 0;

    for (let i = 1; i < HL575_COLUMNS.length; i++) {
        if (
            Math.abs(hl575ColumnREff(HL575_COLUMNS[i][0]) - u) <
            Math.abs(hl575ColumnREff(HL575_COLUMNS[nearest][0]) - u)
        ) {
            nearest = i;
        }
    }

    const start = Math.max(0, Math.min(nearest - 1, HL575_COLUMNS.length - 4));
    const window = HL575_COLUMNS.slice(start, start + 4);
    const nodes = window.map((row) => hl575ColumnREff(row[0]));

    const inv = 10 / height;
    const basis = [
        height / 10,
        1,
        inv,
        inv ** 2,
        inv ** 3,
        inv ** 4,
        inv ** 5,
    ];

    let multiplier = 0;

    for (let a = 0; a < basis.length; a++) {
        let term = 0;

        for (let j = 0; j < window.length; j++) {
            let weight = 1;

            for (let m = 0; m < nodes.length; m++) {
                if (m !== j) {
                    weight *= (u - nodes[m]) / (nodes[j] - nodes[m]);
                }
            }

            term += weight * window[j][a + 1];
        }

        multiplier += term * basis[a];
    }

    return multiplier;
}

// --- CANIMEX/TF D800-120 --------------------------------------------------
// Built the way the 575-120 should have been: the catalog supplies SHAPE, the
// reference calculator supplies NUMBERS.
//
// Geometry, confirmed rather than assumed. Eight 100 lb cycle counts give
//     rEff^2 = 17.0209238 + 0.099661021 * HL   (residual 7e-5)
// so r0 = 4.12564" against the catalog's 4.125, and a pitch of 0.3130943".
// That pitch was PREDICTED as 0.313095" from the 575 before the runs were
// made, and matched to 0.0008%. All three hi-lift drums share one pitch
// constant, and each sits about 0.016% above its catalog radius.
//
// The height axis is measured, not borrowed. A full 16-height sweep at 48" of
// hi-lift (6' to 32') fits the six-term basis to 3.3e-07, and two held-back
// points - 9'6" and 17'0" - were predicted from it and confirmed exactly
// before any of this was written.
//
// WHAT IS EXACT, and what is not:
//   * the entire 48" column, every height from 6' to 32'
//   * 12'0" at 0", 48" and 120" of hi-lift
//   * the sub-12" clamp and the above-120" fallback
// Everywhere else this is the catalog's shape carrying a correction fitted to
// those anchors. The catalog-to-calculator offset is NOT flat in hi-lift -
// measured at 12' it runs -0.0068% at 0", +0.0307% at 48", +0.1399% at 120" -
// so it is modelled as a quadratic through those three points, scaled across
// height by the shape of the measured 48" column. Expect roughly 0.03% between
// anchors, against 0.002% once the remaining columns are measured.
//
// Hi-lift handling differs from a plain clamp and was measured directly:
// below 12" the calculator freezes to the 0" row, and ABOVE 120" it falls back
// to the 0" row as well rather than clamping to the maximum - 125" returns the
// 0" value, while 119" and 120" are distinct valid columns.
const HL800_NODE_A = 17.015618;      // catalog spiral - places the columns
const HL800_NODE_B = 0.099471395;
const HL800_A = 17.0209238;          // calculator spiral - drives rEff
const HL800_B = 0.099661021;
const HL800_MIN = 12;
const HL800_MAX = 120;

// [hiLift, lowest published height, highest published height, a..f]
const HL800_COLUMNS = [
        [  0,  6.0, 22.0, -0.00038451,  0.00215513,  0.88638084, -0.06221330, -0.00225582,  0.00043088],
        [  3,  6.0, 22.0,  0.00032556, -0.00194703,  0.90309410, -0.09348677,  0.00207622, -0.00035216],
        [  6,  6.0, 22.5,  0.00144904, -0.00883012,  0.92677985, -0.13319744,  0.01151697, -0.00230580],
        [  9,  6.0, 22.5, -0.00038534,  0.00249321,  0.90780850, -0.12522878, -0.00443646,  0.00093748],
        [ 12,  6.0, 23.0,  0.00026862, -0.00216825,  0.92803050, -0.16289592,  0.00497505, -0.00118857],
        [ 15,  6.0, 23.0, -0.00065641,  0.00353806,  0.92210475, -0.16914647, -0.00335194,  0.00047555],
        [ 18,  6.0, 23.5,  0.00105011, -0.00664576,  0.95259926, -0.21513078,  0.00911999, -0.00204672],
        [ 21,  6.0, 23.5,  0.00113449, -0.00681916,  0.95966739, -0.23507387,  0.00786839, -0.00180675],
        [ 24,  6.0, 24.0, -0.00106720,  0.00664545,  0.93568005, -0.22110847, -0.01102029,  0.00192390],
        [ 27,  6.0, 24.0,  0.00022764, -0.00137525,  0.96204092, -0.26339244,  0.00007888, -0.00046435],
        [ 30,  6.0, 24.5, -0.00053087,  0.00321819,  0.95858589, -0.27205238, -0.00664894,  0.00067935],
        [ 33,  6.0, 24.5, -0.00009937,  0.00090438,  0.97020967, -0.29596526, -0.00624744,  0.00056908],
        [ 36,  6.0, 25.0,  0.00078583, -0.00517652,  0.99303232, -0.33486118,  0.00339890, -0.00168766],
        [ 39,  6.0, 25.0,  0.00040830, -0.00246049,  0.99292315, -0.34612469, -0.00236718, -0.00077028],
        [ 42,  6.0, 25.5, -0.00027260,  0.00151040,  0.99143609, -0.35725959, -0.00763326, -0.00007900],
        [ 45,  6.0, 25.5,  0.00019692, -0.00164521,  1.00632247, -0.38599390, -0.00388297, -0.00121772],
        [ 48,  6.0, 26.0,  0.00000707, -0.00034423,  1.00975858, -0.40082189, -0.00812069, -0.00066058],
        [ 51,  6.0, 26.0, -0.00052979,  0.00364277,  1.00593961, -0.40686219, -0.01711985,  0.00077046],
        [ 54,  6.0, 26.5,  0.00018444, -0.00152327,  1.02639897, -0.44220881, -0.00975066, -0.00128996],
        [ 57,  6.0, 26.5,  0.00000238,  0.00008420,  1.02839907, -0.45455711, -0.01567517, -0.00053773],
        [ 60,  6.0, 27.0,  0.00023254, -0.00171104,  1.04017150, -0.47951484, -0.01405845, -0.00156523],
        [ 63,  6.0, 27.0,  0.00002304, -0.00063126,  1.04504605, -0.49662458, -0.01674266, -0.00175092],
        [ 66,  6.0, 27.5, -0.00041196,  0.00270439,  1.04231357, -0.50268170, -0.02646304, -0.00042602],
        [ 69,  6.0, 27.5, -0.00028878,  0.00211980,  1.04955945, -0.52032458, -0.02994670, -0.00045626],
        [ 72,  6.0, 28.0, -0.00025474,  0.00170274,  1.05781723, -0.54085593, -0.03095143, -0.00127045],
        [ 75,  6.5, 28.0,  0.00003269, -0.00038062,  1.07003882, -0.56581213, -0.02953546, -0.00273123],
        [ 78,  6.5, 28.5,  0.00070115, -0.00500550,  1.08832815, -0.59698043, -0.02547945, -0.00464856],
        [ 81,  7.0, 28.5,  0.00033722, -0.00274776,  1.09014755, -0.61076843, -0.02936963, -0.00548463],
        [ 84,  7.0, 29.0, -0.00017822,  0.00150639,  1.08336551, -0.60876442, -0.04585502, -0.00285475],
        [ 87,  7.5, 29.0, -0.00009295,  0.00036540,  1.09442926, -0.63372569, -0.04350844, -0.00530826],
        [ 90,  7.5, 29.5, -0.00057091,  0.00395915,  1.09088204, -0.63788264, -0.05503238, -0.00439147],
        [ 93,  8.0, 29.5, -0.00124206,  0.00940852,  1.08035581, -0.62974455, -0.07638534, -0.00077064],
        [ 96,  8.0, 30.0, -0.00056982,  0.00487352,  1.09761146, -0.65773161, -0.07570056, -0.00235701],
        [ 99,  8.5, 30.0,  0.00027795, -0.00173245,  1.12332546, -0.70110487, -0.06226395, -0.00804223],
        [102,  8.5, 30.5,  0.00060725, -0.00526809,  1.14312216, -0.74065963, -0.04838450, -0.01480811],
        [105,  9.0, 30.5, -0.00031458,  0.00191320,  1.12822422, -0.72746514, -0.07223466, -0.01149726],
        [108,  9.0, 31.0, -0.00042611,  0.00315947,  1.12921497, -0.73310736, -0.08653425, -0.00990234],
        [111,  9.5, 31.0, -0.00038829,  0.00354401,  1.13188804, -0.74011240, -0.10030212, -0.00861905],
        [114,  9.5, 31.5,  0.00060624, -0.00531682,  1.16901076, -0.80890179, -0.06091259, -0.02506744],
        [117, 10.0, 31.5, -0.00006326, -0.00032254,  1.16027099, -0.80163244, -0.08417108, -0.02148973],
        [120, 10.0, 32.0,  0.00147607, -0.01376476,  1.21209342, -0.89286040, -0.02810318, -0.04334304],
];

// Correction onto the reference calculator, one curve per measured hi-lift
// column, refitted against 122 six-decimal reference multipliers.
//
// Each row is [hiLift, a, b, c, d, e, f] for
//     offset = a + b*(10/H) + c*(10/H)^2 + ... + f*(10/H)^5
// with the term count per column chosen by leave-one-out, so a thinly
// sampled column cannot overfit.
//
// WHY THIS DRUM KEEPS THE CATALOG AND THE 575-120 DOES NOT. A direct fit,
// throwing the catalog away and building each column from reference data
// alone, was tried and rejected. It reproduces all 122 measured points
// exactly - but this drum has only 9 measured hi-lift columns, spaced 12 to
// 18 inches, and without the catalog underneath, interpolating between them
// costs 1.7e-03. The catalog supplies a 41-column scaffold at 3 inch
// spacing, which is structure no amount of reference data here replaces.
// The 575-120 could go direct because it has 15 columns.
//
// Accuracy: worst 3.1e-05, median 2.9e-06 across all 122 points, of which
// 65 were never used to fit it. That is roughly 8x better than the previous
// build. Nothing is exact to 6 decimals, and cannot be: the catalog prints
// 4, so its rounding is the floor.
//
// MORE RUNS WILL NOT FIX THAT, which was measured rather than assumed.
// Subsampling the catalog at 18, 12, 9 and 6 inch column spacing gives
// interpolation errors of 2.0e-04, 1.6e-04, 1.0e-04 and 1.1e-04 - tripling
// the runs from 84 to 252 moves the median not at all. The error sits on
// the bottom row of each column, where the multiplier collapses toward zero
// and the surface turns faster than any practical spacing follows. Exactness
// at every whole inch of hi-lift from 12 to 120 would need 109 columns,
// about 1300 runs.
const HL800_OFFSET_COLUMNS = [
        [  0,    0.0000668730,    0.0000000000,    0.0000000000,    0.0000000000,    0.0000000000,    0.0000000000],
        [ 18,    0.0001187193,    0.0000520070,    0.0000000000,    0.0000000000,    0.0000000000,    0.0000000000],
        [ 36,    0.0001477844,    0.0001290967,    0.0000000000,    0.0000000000,    0.0000000000,    0.0000000000],
        [ 48,    0.0003995922,   -0.0002475937,    0.0002426016,    0.0000000000,    0.0000000000,    0.0000000000],
        [ 66,    0.0010749243,   -0.0044286410,    0.0092568029,   -0.0076372031,    0.0023287213,    0.0000000000],
        [ 78,   -0.0046636031,    0.0369272645,   -0.1019315952,    0.1338522575,   -0.0834740707,    0.0200444264],
        [ 96,    0.0002540913,    0.0001379090,    0.0026766379,   -0.0049721575,    0.0029970599,    0.0000000000],
        [108,    0.0023154905,   -0.0122893279,    0.0297245819,   -0.0298609333,    0.0116230522,    0.0000000000],
        [120,   -0.0090575428,    0.0851109694,   -0.2939191042,    0.4957483924,   -0.4055693673,    0.1297975767],
];

function hl800Applied(hiLiftInches) {
    const hl = Number(hiLiftInches) || 0;

    return hl < HL800_MIN || hl > HL800_MAX ? 0 : hl;
}

function hl800REff(hiLiftInches) {
    return Math.sqrt(HL800_A + HL800_B * hl800Applied(hiLiftInches));
}

function hl800Node(hiLift) {
    return Math.sqrt(HL800_NODE_A + HL800_NODE_B * hiLift);
}

function hl800Basis(height) {
    const inv = 10 / height;

    return [height / 10, 1, inv, inv ** 2, inv ** 3, inv ** 4];
}

// The published surface, before the correction onto the calculator.
function hl800Base(height, hiLift) {
    const u = hl800Node(hiLift);

    let nearest = 0;

    for (let i = 1; i < HL800_COLUMNS.length; i++) {
        if (
            Math.abs(hl800Node(HL800_COLUMNS[i][0]) - u) <
            Math.abs(hl800Node(HL800_COLUMNS[nearest][0]) - u)
        ) {
            nearest = i;
        }
    }

    const start = Math.max(0, Math.min(nearest - 1, HL800_COLUMNS.length - 4));
    const window = HL800_COLUMNS.slice(start, start + 4);
    const nodes = window.map((row) => hl800Node(row[0]));
    const basis = hl800Basis(height);

    let value = 0;

    for (let a = 0; a < 6; a++) {
        let term = 0;

        for (let j = 0; j < window.length; j++) {
            let weight = 1;

            for (let m = 0; m < nodes.length; m++) {
                if (m !== j) {
                    weight *= (u - nodes[m]) / (nodes[j] - nodes[m]);
                }
            }

            term += weight * window[j][a + 3];
        }

        value += term * basis[a];
    }

    return value;
}

function hl800Multiplier(heightFeet, hiLiftInches) {
    const height = Number(heightFeet) || 0;

    if (height <= 0) {
        return 0;
    }

    const hl = hl800Applied(hiLiftInches);
    const base = hl800Base(height, hl);
    const u = hl800Node(hl);

    let nearest = 0;

    for (let i = 1; i < HL800_OFFSET_COLUMNS.length; i++) {
        if (
            Math.abs(hl800Node(HL800_OFFSET_COLUMNS[i][0]) - u) <
            Math.abs(hl800Node(HL800_OFFSET_COLUMNS[nearest][0]) - u)
        ) {
            nearest = i;
        }
    }

    const start = Math.max(
        0,
        Math.min(nearest - 1, HL800_OFFSET_COLUMNS.length - 3)
    );
    const window = HL800_OFFSET_COLUMNS.slice(start, start + 3);
    const nodes = window.map((row) => hl800Node(row[0]));

    const inv = 10 / height;
    const shape = [1, inv, inv ** 2, inv ** 3, inv ** 4, inv ** 5];

    let offset = 0;

    for (let a = 0; a < shape.length; a++) {
        let term = 0;

        for (let j = 0; j < window.length; j++) {
            let weight = 1;

            for (let m = 0; m < nodes.length; m++) {
                if (m !== j) {
                    weight *= (u - nodes[m]) / (nodes[j] - nodes[m]);
                }
            }

            term += weight * window[j][a + 1];
        }

        offset += term * shape[a];
    }

    return base * (1 + offset);
}


// --- Hi-Lift drums --------------------------------------------------------
// A hi-lift drum is a different animal from the standard drums above. The
// cable no longer sees one profile: the high-lift extension winds on a flat
// spiral section, and the door-height portion on its own section. Two things
// follow, both confirmed across 175 reference values:
//
//   1. rEff depends on the HI-LIFT ONLY, never on door height. A full 4-10 ft
//      sweep returns an identical cycle count at every hi-lift tried (3998 at
//      12", 2949 at 24", 2253 at 36", 1991 at 42", 1583 at 54"), and peak
//      torque is weight * rEff, so rEff is pinned by hi-lift alone.
//
//   2. rEff^2 is EXACTLY LINEAR in hi-lift. d(rEff^2)/dHL measures
//      0.0996617 +/- 1e-6 at every hi-lift with a 6-digit cycle count. That is
//      flat-spiral cable geometry and not a fit:
//
//          r(n) = r0 + p*n   =>   L = pi*(r^2 - r0^2)/p
//                            =>   rEff^2 = r0^2 + (p/pi)*HL
//
//      giving a base radius r0 = sqrt(A) = 2.719421" and a cable pitch
//      p = pi*B = 0.313097". The independently measured sub-12" clamp value is
//      2.7194206 - the same number to 6e-7, so the clamp is simply HL = 0 on
//      this curve rather than a constant of its own.
//

// Unlike the standard drums, it is the MULTIPLIER - not the turns - that is
// smooth in door height here, and it follows the very same 6-term family the
// standard drums use for turns:
//
//     multiplier = a*H + b + c/H + d/H^2 + e/H^3 + f/H^4
//     turns      = rEff / multiplier
//
// That ordering is forced by the data, not chosen. At 54" of hi-lift the
// multiplier collapses through zero just under 4 ft, so turns has a genuine
// pole there (the reference prints 1620.05 turns and a 3858.95" spring at
// 4'0"/54"). Fitting TURNS with the 6-term form misses by 362%; fitting the
// MULTIPLIER with it lands at 0.0009%, and the pole falls out for free.
//
// Each of a..f is then a quintic in u = rEff - r0, interpolated through the
// six measured hi-lift columns (0/12/24/36/42/54). rEff is used as the
// interpolation variable rather than hi-lift itself because it halves the
// residual - it is the drum's own geometric coordinate.
//
// Held out from the fit entirely and then predicted: 7'3"/30" and 5'6"/42"
// came back within 2e-6 and 4e-6, and 6'6"/12" was predicted at 0.484240
// before the reference confirmed 0.484240 exactly.
//
// Accuracy: 169 of the 175 reported display values reproduce exactly. The six
// that do not are last-digit rounding at a boundary - three turns cells, and
// the 4'0"/54" pole row, where the reference's own 6-decimal multiplier
// (0.002206) carries only 4 significant figures and 1/multiplier amplifies it
// into a 0.09" spring-length difference. A 3721-point search over the spiral
// constants found no setting that does better; the residual conflict is
// between the reference's displayed turns and its displayed cycles, which
// disagree by 0.003% at 36" and 54" under this file's cycle law.
// maxHiLift is the most hi-lift each drum accepts. As with the standard
// drums, the trailing number in the name is the rating: 120, 120 and 54.
// Past it the entry is refused rather than extrapolated - which matters here,
// because the fitted curves go NEGATIVE above the measured band and would
// otherwise hand back a confident-looking wrong answer.
const HILIFT_DRUMS = {
    "CANIMEX/TF D800-120": {
        maxHiLift: 120,
        maxHeight: 384,
        maxWeight: 2200,
        // 2200 lb and 384 inches, from the reference's own drum record. The
        // earlier note here said there was no weight cap because the reference
        // tracked the entered weight exactly to 2000 lb - which it does, since
        // 2000 is under 2200. Measuring inside a limit cannot find it.
        catalog: true,
        reff: hl800REff,
        multiplier: hl800Multiplier,
    },
    // Catalog-built. See the HL575_* block above for how it differs from the
    // reverse-engineered drums, and why.
    "CANIMEX/TF 575-120": {
        maxHiLift: 120,
        maxWeight: 1000,
        maxHeight: 264,
        catalog: true,
        reff: hl575REff,
        multiplier: hl575Multiplier,
    },
    "CANIMEX/TF 525-54HL": {
        maxHiLift: 54,
        maxWeight: 1000,
        maxHeight: 234,
        spiralA: 7.3952515,      // r0^2
        spiralB: 0.099661766,    // p/pi
        multCoeffs: [
            [-1.319237311599656e-06, -0.0016344760924833605, 0.01669819788227263, -0.05573510317140107, 0.07466492981829372, -0.0344128621693411],
            [3.960125905526815e-05, 0.052452637217159974, -0.5361653881591721, 1.7935526153774979, -2.4067095438958654, 1.1086242783026363],
            [3.86960178358562, 0.7692767006011653, 6.685863406482316, -22.407748517920883, 30.094803859189586, -13.828953800792886],
            [-2.900256482837781, -13.655562511737713, -40.29346731987498, 136.39394326043143, -181.4331247650827, 82.83811944656046],
            [-0.005522552882827296, -11.399633134303011, 114.0215025064608, -405.13917233690313, 521.183049546905, -233.07046922855912],
            [0.005265468793582319, 12.364865160322623, -125.95235614710633, 418.9639666876059, -550.4250674078384, 221.4245107209963],
        ],
    },
};

// Hi-lift actually used by the model: anything under a full 12" behaves as 0.
function hiLiftApplied(hiLiftInches) {
    const hl = Number(hiLiftInches) || 0;

    return hl >= HILIFT_MIN ? hl : 0;
}

function hiLiftREff(drum, hiLiftInches) {
    return Math.sqrt(drum.spiralA + drum.spiralB * hiLiftApplied(hiLiftInches));
}

function hiLiftMultiplier(drum, heightFeet, hiLiftInches) {
    const height = Number(heightFeet) || 0;

    if (height <= 0) {
        return 0;
    }

    // u is measured from the drum's base radius so the quintics stay
    // well conditioned - u runs 0 to 0.855 over the whole hi-lift range.
    const u = hiLiftREff(drum, hiLiftInches) - Math.sqrt(drum.spiralA);

    const basis = [
        height,
        1,
        1 / height,
        1 / height ** 2,
        1 / height ** 3,
        1 / height ** 4,
    ];

    let multiplier = 0;

    for (let i = 0; i < basis.length; i++) {
        const coeffs = drum.multCoeffs[i];

        // Horner, highest power first.
        let term = 0;

        for (let j = coeffs.length - 1; j >= 0; j--) {
            term = term * u + coeffs[j];
        }

        multiplier += term * basis[i];
    }

    return multiplier;
}

// --- Track radius --------------------------------------------------------
// The Radius control (12", 15", LHR) applies to standard lift only - hi-lift
// forces 15 and vertical hides the row. Until now it was written to state and
// read by nothing, so all three settings gave identical results.
//
// It changes TURNS AND NOTHING ELSE. Across 62 reference runs the cycle count
// never moved - 13,045 at all three radii on the D400-96 - and cycle life
// depends only on weight * rEff / springs, so rEff is untouched. Confirmed
// directly too: multiplier * turns comes to 2.27548 / 2.27635 / 2.27532
// against a stored rEff of 2.27535. So spring length, spring weight and cycle
// life all follow from the turns change with nothing else to model.
//
// Radius 15 is the baseline the drum curves above were built on. 12" and LHR
// each REMOVE turns, by an amount that shrinks as the door gets taller:
// on the D400-96, 0.303 turns at 7 ft against 0.250 at 14 ft for radius 12.
// Neither a constant offset nor a constant ratio fits - both were tried
// against measurements and both missed.
//
// The drop is a property of the TRACK, not the drum, which shows up as
// drop * rEff being nearly constant across drums - the track removes a fixed
// length of CABLE, and turns = cable / (2*pi*r). Tempting to ship that as one
// shared curve, and it was tried: it predicts the D400-144 to 1e-04 but misses
// the D525-216 by up to 1.7e-02, because that drum's taper puts the affected
// cable at a different radius. So each drum carries its own pair, fitted from
// 62 reference multipliers over 6-22 ft.
//
// 55 of the 62 reproduce exactly at 6 decimals; the rest miss in the seventh.
// Between measured heights the curves hold to 1e-06 (D400-96) and 1e-04
// (D400-144), the difference being how many heights each has.
//
//     turns(radius) = turns(15) - (a + b/H + c/H^2 + d/H^3 + e/H^4 + f/H^5)
const RADIUS_TURN_DROP = {
    "CANIMEX/TF D400-144|12": [0.1656285206, 2.3076617446, -30.0048033058, 260.8643203117, -1078.6832652560, 1784.5220533614],
    "CANIMEX/TF D400-144|LHR": [0.5135293100, 2.8661567110, -28.2453217629, 251.8661379208, -1028.4071457077, 1692.6747680490],
    "CANIMEX/TF D400-96|12": [0.2111860473, 0.4705702303, 0.6897970776, 7.1265035538, -37.9881874300, 92.1914437055],
    "CANIMEX/TF D400-96|LHR": [0.5640194687, 0.9484105635, 3.6996361562, -9.5661849635, 29.6419173980, 0.0000000000],
    "CANIMEX/TF D525-216|12": [0.1506627488, 0.8904460305, -7.6392969827, 70.2416578278, -283.0436720321, 468.7138807192],
    "CANIMEX/TF D525-216|LHR": [0.4206159324, 1.4306546927, -8.1013920108, 81.1690285358, -327.0608469821, 548.1638483334],
};

// Turns removed by the selected track radius. Radius 15 is the baseline, and
// anything without a measured curve - including hi-lift and vertical, which
// do not offer the choice - drops nothing.
function radiusTurnDrop(drumName, radius, heightFeet) {
    const coefficients = RADIUS_TURN_DROP[drumName + "|" + radius];
    const height = Number(heightFeet) || 0;

    if (!coefficients || height <= 0) {
        return 0;
    }

    const inv = 1 / height;

    return (
        coefficients[0] +
        coefficients[1] * inv +
        coefficients[2] * inv ** 2 +
        coefficients[3] * inv ** 3 +
        coefficients[4] * inv ** 4 +
        coefficients[5] * inv ** 5
    );
}

// The selectable wire sizes, ascending. MUST match the Wire Size dropdown in
// the template - the auto-selection below walks this list and picks the first
// entry that meets the cycle target, so a size present in one and not the
// other would either be unreachable or offered and never chosen.
// 0.2" IS NOT ON THIS LADDER, and its absence is measured rather than assumed.
// Across 10,545 springs the reference has quoted, it has used 35 distinct wire
// sizes and 0.2" is not one of them, while both of its neighbours are ordinary:
//
//     0.1875"  25 times      0.2"      0 times
//     0.192"   19 times      0.207"   66 times
//
// A size that never appears between two that do is not a sampling gap. It is
// also observed directly: on a 4-spring 575-120 door at 60" hi-lift, stepping
// the weight a pound at a time, the reference goes straight from 0.192" to
// 0.207" at 180 lb. We stopped at 0.2" on the way and so quoted a wire the
// reference does not sell, with the spring length and now the price that go
// with it.
//
// THE REST OF THE LADDER IS CONFIRMED BY THE SAME SWEEP. Seven of the eight
// switch weights in it already matched to the pound - 129, 144, 169, 222, 259,
// 282 and 314 - so the cycle model that chooses the wire was never the
// problem. 0.2" was the only rung that did not belong.
//
// The six sizes below 0.17" have never been seen either, but they sit BELOW
// the thinnest the reference has ever returned rather than inside the range,
// so their absence is as easily explained by no door being that light. They
// stay until something measures them.
const WIRE_SIZES = [
    0.125, 0.135, 0.142, 0.1483, 0.1562, 0.162, 0.17, 0.177, 0.1875, 0.192,
    0.207, 0.2187, 0.2253, 0.2343, 0.2437, 0.25, 0.2625, 0.273, 0.283,
    0.289, 0.295, 0.3065, 0.3125, 0.3195, 0.331, 0.3437, 0.3625, 0.375,
    0.3938, 0.4062, 0.4218, 0.4305, 0.4375, 0.4531, 0.4615, 0.4687, 0.49,
    0.5, 0.5312, 0.5625, 0.625,
];

// Back to the exact string the dropdown uses, so the select matches.
function formatWire(wire) {
    return String(wire) + '"';
}

// What the info panel shows for each drum, in display order.
//
// All six drums now carry supplied figures rather than catalog readings, and
// every one shows the same three rows, so the panel reads the same whichever
// drum is selected.
//
// The hi-lift entries used to carry max hi-lift, cable capacity of flat and
// drum radius as well; those are gone. Max hi-lift in particular was worth
// removing rather than correcting - it read 118" and 119" from the catalog
// where the entry is actually bounded at 120", so the panel and the warning
// disagreed on screen.
//
// The earlier max weights were INFERRED, by doubling the catalog's load per
// drum on the theory that a door hangs on two. The supplied figures came back
// 1000, 1000 and 2200, which is exactly what that doubling predicted, so the
// assumption held on the hi-lift drums as it had on the standard ones.
const DRUM_INFO = {
    "CANIMEX/TF D400-96": [
        ["Max Height", '96"'],
        ["Max Weight", "530 lb"],
        ["Max Cable Diameter", '1/8"'],
    ],
    "CANIMEX/TF D400-144": [
        ["Max Height", '144"'],
        ["Max Weight", "750 lb"],
        ["Max Cable Diameter", '5/32"'],
    ],
    "CANIMEX/TF D525-216": [
        ["Max Height", '216"'],
        ["Max Weight", "1500 lb"],
        ["Max Cable Diameter", '3/16"'],
    ],
    "CANIMEX/TF 525-54HL": [
        ["Max Height", '234"'],
        ["Max Weight", "1000 lb"],
        ["Max Cable Diameter", '3/16"'],
    ],
    "CANIMEX/TF 575-120": [
        ["Max Height", '264"'],
        ["Max Weight", "1000 lb"],
        ["Max Cable Diameter", '3/16"'],
    ],
    "CANIMEX/TF D800-120": [
        ["Max Height", '384"'],
        ["Max Weight", "2200 lb"],
        ["Max Cable Diameter", '1/4"'],
    ],
};

// --- DUPLEX -------------------------------------------------------------
// A duplex set is two springs wound one inside the other. They are sized
// together, and the reference calculator reports them separately.
//
// REVERSE-ENGINEERED FROM 17 REFERENCE READINGS. Everything here is measured,
// not derived - see the notes on each piece for what is solid and what is a
// bracket.
//
// THE LENGTH RULE, which took the longest to find:
//
//     x = C / TIPPT
//     round x to the nearest whole inch, TIES GOING DOWN
//     inner length = that whole inch, PLUS 0.25" if x rounded UP
//     outer length = inner + 1
//
// The 0.25" is not a regime or a fudge: it appears exactly when the rounding
// goes up and not when it goes down. Two readings a hair apart proved it -
// at 460 lb x is 15.597 and rounds up to 16.25, at 470 lb x is 15.265 and
// rounds down to 15.00. A 1.25" step for a 2% change in load, which no smooth
// formula reproduces. It is also why 2 5/8" inside 5 1/4" never shows a
// quarter: its x lands on 35.000, 26.250, 21.000 and 17.500, every one of
// which rounds down or ties.
//
// WIRES. Both start at the minimum for their spring ID and step UP together
// as the load grows: the reference takes the FIRST combination whose cycle
// count reaches the target, which is what duplexStep below evaluates.
//
// This was originally a TIPPT threshold per step, fitted to the 7'0" readings,
// and it was WRONG. Cycle life depends on torque, which is rate times TURNS,
// and turns grows with door height - so at 11'2" a door needs a bigger wire
// than the same TIPPT at 7'0" does. A 572 lb 11'2" door came back one wire
// size light, at 9,000 cycles against a 10,000 target, with the app's own
// cycle figure already showing it had missed. Evaluating the target directly
// has no such blind spot and needs no thresholds at all.
//
// C and K are per WIRE COMBINATION, not per spring pair: changing either wire
// changes both.
//
// THEY ARE ALSO PER SPRING COUNT, and every reading behind them was taken at
// TWO springs. The catalog settles how they scale:
//
//     LENGTH OF ACTIVE COILS = SPRING QTY x DIVIDER / IPPT
//
// so the active length is PROPORTIONAL to the spring quantity, and C scales
// with it. K is body length times TIPPT and the body scales the same way, so
// K does too. Both are therefore multiplied by springs/2 at the point of use
// - see duplexSpringScale. Before this they were used raw, which meant the
// spring count changed nothing at all in Duplex. C sets the length, K sets the cycle count (K = body length x
// TIPPT, recovered by inverting the reported cycles).
//
// C IS VERY SLIGHTLY HEIGHT-DEPENDENT, which three heights now expose. For
// the 0.2625/0.2253 combination the 7'0" readings want C >= 2080.9 while a
// 350 lb 9'0" door wants C < 2079.5 - a 0.07% disagreement. Tiny, but the
// length rule rounds to the whole inch, so a reading whose x sits within
// 0.001 of a rounding boundary can come out a quarter inch either way. One
// of the 14 readings for that combination does. Every other reading is
// reproduced exactly, and the chosen C is the value that reproduces the most.
//
// COVERAGE AND ACCURACY, measured by replaying all reference readings:
//
//   spring IDs, wire sizes, lengths, weights   EXACT on all 20
//   cycle counts                               13 exact, worst case 3.6% out
//
// K IS CONSTANT ACROSS DOOR HEIGHTS. An earlier note here claimed it was not,
// on the strength of the 7' readings giving 2017 against the 10' one's 2036.
// That was wrong, and the way it was wrong is worth recording.
//
// Six responses straight from the reference's own API - one wire combination,
// 300 lb, heights 84" to 144" - invert to K = 2020.4, 2021.2, 2024.6, 2022.5,
// 2026.5, 2025.8. A 0.30% spread, which is constant.
//
// The apparent height dependence came from MY TURNS CURVE, not from K: at
// those heights it runs -0.25% to +0.52% against the reference's own turns,
// and cycle life goes as turns^-4.67, so half a percent of turns is well over
// two percent of cycles. The cycle model was never the problem.
//
// What is left is bounded at roughly 2-3%, from that turns error plus the
// reference rounding its own TIPPT and turns to one decimal before using
// them. Lengths are unaffected and exact.
//
// Outside the wire combinations listed, the last step is used and the answer
// will drift - duplexCalibrated reports which case you are in.
// C AND tau ARE NO LONGER READ. The length now comes from the catalog formula
// (see duplexActiveLength), which has no fitted constant, so every C, cSlope,
// cIntercept and tau below is dead weight. They are KEPT, not deleted, for one
// reason: if the 0.25" step turns out to be real after all - see the
// superseded 460/470 lb entries in dev/corpus.json - this is the only record
// of the fit that produced it. Delete them once that is settled.
//
// K IS STILL LIVE. It sets the cycle count, and the cycle model is the part
// that is still wrong: inverting the reference's own counts needs 3-5% more
// inner-spring torque than the physical active length gives, and no single
// factor reconciles all six readings.
const DUPLEX_PAIRS = {
    // --- THE CATALOGUE -------------------------------------------------
    // Seventeen wire pairings, every one of them OBSERVED in a reference
    // response, with K derived by inverting the reference's own reported cycle
    // count rather than fitted to a bracket midpoint.
    //
    // HOW K IS OBTAINED. For a reading with a reported cycle count,
    //
    //     torque = CYCLE_COEFFICIENT * wire^CYCLE_WIRE_EXPONENT
    //                  / cycles^(1/CYCLE_EXPONENT)
    //     body   = divider_inner * turns / torque
    //     K      = body * TIPPT / (springs / 2)
    //
    // which is the cycle model run backwards. Where a pairing has several
    // readings the median is taken and `n` records how many agreed; the spread
    // column below is how far apart they were, and it is small enough that the
    // cycle counts are rounded to the nearest thousand and little else:
    //
    //     0.2625/0.2253  n=10  spread 0.76%
    //     0.273/0.2253   n= 9  spread 1.47%
    //     0.289/0.2343   n= 9  spread 2.05%
    //     0.375/0.3065   n= 2  spread 0.17%
    //     0.283/0.2343   n= 2  spread 1.51%
    //
    // Pairings with n=1 are a single reading and so carry that reading's
    // rounding, about 1% in K. They are still far better than what they
    // replace: the old values were bracket midpoints or a line extrapolated
    // past its data, and seven of these rungs had no entry at all.
    //
    // K/S runs 0.88 to 0.99, so K is close to the physical stiffness but not
    // equal to it, and the deviation is per pairing - see duplexCyclesForStep.
    //
    // C AND tau ARE GONE. Both belonged to the old length rule, which is now
    // the catalog formula in duplexActiveLength and has no fitted constant.
    '3 3/4" inside 6"': {
        innerId: 3.75,
        outerId: 6,
        calibration: [
            { outerWire: 0.2625, innerWire: 0.2253, K: 2022.2, n: 1199, sMult: 1.047, twoOffset: 0.25, lineByCount: { 1: { a: 1.00237, b: -0.0105, lo: 0, hi: 1 }, 2: { a: -0.34735, b: 0.0435, a2: 0.76639, b2: -0.0005, lo: 0.25, mid: 0, hi: 1.25 }, 3: { a: 0.76853, b: -0.001, lo: 0.25, hi: 1.25 }, 4: { a: 0.77469, b: -0.001, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.273, innerWire: 0.2253, K: 2255.4, n: 370, sMult: 1.0085, lineByCount: { 2: { a: 0.75739, b: -0.0095, a2: 0.6804, b2: 0.008, lo: 0, mid: 1.25, hi: 1 }, 3: { a: 0.8286, b: -0.0105, lo: 0.25, hi: 1.25 }, 4: { a: 0.74678, b: -0.0095, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.283, innerWire: 0.2253, K: 2452.9, n: 324, sMult: 0.98975, lineByCount: { 1: { a: 0.73007, b: -0.002, lo: 0, hi: 1 }, 2: { a: 0.72757, b: -0.0005, lo: 0, hi: 1 }, 3: { a: 0.69906, b: 0.0005, lo: 0.25, hi: 1.25 }, 4: { a: 0.77217, b: -0.0025, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.283, innerWire: 0.2343, K: 2717.0, n: 112, sMult: 1.0115, lineByCount: { 2: { a: 0.61566, b: -0.005, a2: 0.5923, b2: 0.0155, lo: 0, mid: 1.25, hi: 1 }, 3: { a: 0.45162, b: 0.0015, lo: 0.25, hi: 1.25 }, 4: { a: 0.75366, b: -0.0095, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.289, innerWire: 0.2343, K: 2879.1, n: 321, sMult: 0.99825, lineByCount: { 1: { a: 0.74836, b: -0.009, lo: 0, hi: 1 }, 2: { a: 0.66294, b: -0.0035, lo: 0, hi: 1 }, 3: { a: 0.6027, b: -0.0025, lo: 0.25, hi: 1.25 }, 4: { a: 0.64702, b: -0.0065, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.295, innerWire: 0.2343, K: 2980.9, n: 295, sMult: 0.98725, lineByCount: { 1: { a: 0.61123, b: 0, lo: 0, hi: 1 }, 2: { a: 0.61589, b: 0.001, lo: 0, hi: 1 }, 3: { a: 0.78874, b: -0.005, lo: 0.25, hi: 1.25 }, 4: { a: 0.6732, b: -0.0015, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.295, innerWire: 0.2437, K: 3318.5, n: 262, sMult: 1.0115, lineByCount: { 1: { a: 0.5776, b: -0.0035, lo: 0, hi: 1 }, 3: { a: 0.74965, b: -0.009, lo: 0.25, hi: 1.25 }, 4: { a: 0.67565, b: -0.007, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 20, below: { a: 0.554, b: 0, cuts: [0.99393], levels: [0, 1, 1.25] }, above: { a: 0.56892, b: -0.003, cuts: [0.56892], levels: [0, 1, 1.25] } } } },
            { outerWire: 0.3065, innerWire: 0.2437, K: 3617.5, n: 322, sMult: 0.9865, lineByCount: { 2: { a: 0.4994, b: 0.0025, lo: 0, hi: 1 }, 3: { a: 0.64832, b: -0.004, lo: 0.25, hi: 1.25 }, 4: { a: 0.59911, b: -0.002, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3065, innerWire: 0.25, K: 3902.4, n: 58, sMult: 1.01375, twoOffset: 0.25, lineByCount: { 2: { a: -0.16501, b: 0.016, lo: 0.25, hi: 1.25 }, 3: { a: 0.68129, b: 0.0025, lo: 0.25, hi: 1.25 }, 4: { a: 0.8003, b: -0.004, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3125, innerWire: 0.25, K: 4102.8, n: 179, lineByCount: { 3: { a: 0.61268, b: 0.0055, lo: 0.25, hi: 1.25 }, 4: { a: 0.62334, b: 0.0055, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3125, innerWire: 0.2625, K: 4562.2, n: 18, sMult: 1.02875, twoOffset: 0.25, byCount: { 2: [{ upTo: 0.058, bonus: 0 }, { upTo: 0.236, bonus: 0.25 }, { upTo: 0.64, bonus: 0 }, { upTo: 1, bonus: 1.25 }] }, lineByCount: { 3: { a: -2.85594, b: 0.25, lo: 0.25, hi: 1.25 }, 4: { a: 0.91891, b: -0.014, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3195, innerWire: 0.2625, K: 4863.2, n: 320, sMult: 1.013, lineByCount: { 1: { a: 0.60361, b: -0.0035, lo: 0, hi: 1 }, 3: { a: 0.55898, b: -0.0015, lo: 0.25, hi: 1.25 }, 4: { a: 0.59771, b: -0.0035, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 31, below: { a: 0.52743, b: 0, a2: 0.58849, b2: 0.0105, lo: 0, mid: 1.25, hi: 1 }, above: { a: 0.49085, b: 0.0005, lo: 0, hi: 1.25 } } } },
            { outerWire: 0.331, innerWire: 0.2625, K: 5221.6, n: 394, sMult: 0.98725, lineByCount: { 1: { a: 0.50719, b: 0, lo: 0, hi: 1 }, 2: { a: 0.53534, b: -0.001, lo: 0, hi: 1 }, 3: { a: 0.50274, b: 0.0005, lo: 0.25, hi: 1.25 }, 4: { a: 0.49511, b: 0.0005, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.331, innerWire: 0.273, K: 5842.8, n: 250, sMult: 1.02225, twoOffset: 0.25, lineByCount: { 1: { a: 0.53151, b: 0.004, lo: 0, hi: 1 }, 3: { a: 0.35228, b: 0.0095, lo: 0.25, hi: 1.25 }, 4: { a: 0.64904, b: 0.0015, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 24, below: { a: 0.49135, b: 0.0065, a2: 0.65465, b2: 0.012, lo: 0, mid: 1.25, hi: 1 }, above: { a: -0.55441, b: 0.023, a2: 0.33178, b2: 0.009, lo: 0.25, mid: 0, hi: 1.25 } } } },
            { outerWire: 0.3437, innerWire: 0.273, K: 6333.9, n: 323, sMult: 0.99, lineByCount: { 1: { a: 0.4826, b: 0.0005, lo: 0, hi: 1 }, 3: { a: 0.4605, b: 0.0015, lo: 0.25, hi: 1.25 }, 4: { a: 0.54094, b: 0.0005, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3437, innerWire: 0.283, K: 7005.7, n: 230, sMult: 1.0175, lineByCount: { 1: { a: 0.4572, b: 0.0015, lo: 0, hi: 1 }, 3: { a: 0.58641, b: -0.0015, lo: 0.25, hi: 1.25 }, 4: { a: 0.45715, b: 0.001, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 22, below: { a: -0.11221, b: 0.0285, cuts: [0.23971], levels: [0, 1.25, 1] }, above: { a: -0.58046, b: 0.0185, a2: 0.44189, b2: 0.0015, lo: 0.25, mid: 0, hi: 1.25 } } } },
            { outerWire: 0.3625, innerWire: 0.283, K: 7561.9, n: 322, sMult: 0.97875, lineByCount: { 1: { a: 0.37179, b: 0.003, lo: 0, hi: 1 }, 2: { a: 0.3783, b: 0.003, lo: 0, hi: 1 }, 3: { a: 0.41187, b: 0.0025, lo: 0.25, hi: 1.25 }, 4: { a: 0.13142, b: 0.006, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3625, innerWire: 0.289, K: 8386.5, n: 323, sMult: 0.99475, lineByCount: { 1: { a: 0.36574, b: 0.004, lo: 0, hi: 1 }, 2: { a: 0.37617, b: 0.0035, lo: 0, hi: 1 }, 3: { a: 0.31434, b: 0.0045, lo: 0.25, hi: 1.25 }, 4: { a: 0.18567, b: 0.007, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3625, innerWire: 0.295, K: 8881.9, n: 119, sMult: 1.009, lineByCount: { 1: { a: 0.4061, b: 0.0015, lo: 0, hi: 1 }, 3: { a: 0.38513, b: 0.002, lo: 0.25, hi: 1.25 }, 4: { a: 0.45384, b: 0, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 35, below: { a: -3.9841, b: 0.1675, lo: 0, hi: 1 }, above: { a: 0.39901, b: 0.002, lo: 0, hi: 1.25 } } } },
            { outerWire: 0.375, innerWire: 0.295, K: 9281.2, n: 320, sMult: 0.9865, lineByCount: { 1: { a: 0.31367, b: 0.0055, lo: 0, hi: 1 }, 2: { a: 0.34741, b: 0.0045, lo: 0, hi: 1 }, 3: { a: 0.28349, b: 0.0065, lo: 0.25, hi: 1.25 }, 4: { a: 0.33256, b: 0.003, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.375, innerWire: 0.3065, K: 10594.4, n: 320, sMult: 1.0165, lineByCount: { 1: { a: 0.30402, b: 0.0065, lo: 0, hi: 1 }, 3: { a: 0.37028, b: 0.005, lo: 0.25, hi: 1.25 }, 4: { a: 0.19849, b: 0.0105, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 40, below: { a: 0.26904, b: 0.0075, a2: -0.0559, b2: 0.0305, lo: 0, mid: 1.25, hi: 1 }, above: { a: -0.64602, b: 0.016, a2: 0.53677, b2: 0.002, lo: 0.25, mid: 0, hi: 1.25 } } } },
            { outerWire: 0.3938, innerWire: 0.3065, K: 11208.9, n: 300, sMult: 0.9775, lineByCount: { 1: { a: 0.20502, b: 0.005, lo: 0, hi: 1 }, 2: { a: 0.23625, b: 0.0045, lo: 0, hi: 1 }, 3: { a: 0.26294, b: 0.0035, lo: 0.25, hi: 1.25 }, 4: { a: 0.02389, b: 0.0105, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3938, innerWire: 0.3125, K: 12334.2, n: 271, sMult: 0.99275, lineByCount: { 1: { a: 0.22488, b: 0.0055, lo: 0, hi: 1 }, 2: { a: 0.18559, b: 0.006, lo: 0, hi: 1 }, 3: { a: 0.41668, b: 0.001, lo: 0.25, hi: 1.25 }, 4: { a: -0.5779, b: 0.018, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.3938, innerWire: 0.3195, K: 13265.8, n: 123, sMult: 1.00975, lineByCount: { 1: { a: 0.23879, b: 0.005, lo: 0, hi: 1 }, 2: { a: 0.24783, b: 0.005, a2: 0.34257, b2: 0.009, lo: 0, mid: 1.25, hi: 1 }, 3: { a: 0.43013, b: 0.003, lo: 0.25, hi: 1.25 }, 4: { a: -3.81438, b: 0.0995, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4062, innerWire: 0.3195, K: 13744.5, n: 148, sMult: 0.98575, lineByCount: { 1: { a: 0.22157, b: 0.0035, lo: 0, hi: 1 }, 2: { a: 0.29369, b: 0.0035, lo: 0, hi: 1 }, 3: { a: 0.1991, b: 0.0045, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4062, innerWire: 0.331, K: 15603.4, n: 170, sMult: 1.012, lineByCount: { 1: { a: 0.12035, b: 0.006, lo: 0, hi: 1 }, 3: { a: 0.06534, b: 0.0065, lo: 0.25, hi: 1.25 }, 4: { a: -0.0997, b: 0.0085, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 26, below: { a: -0.1978, b: 0.0195, a2: 0.49714, b2: 0, lo: 0, mid: 1.25, hi: 1 }, above: { a: 0.09855, b: 0.007, cuts: [0.09855], levels: [0, 1, 1.25] } } } },
            { outerWire: 0.4218, innerWire: 0.331, K: 16369.3, n: 155, sMult: 0.9855, lineByCount: { 1: { a: 0.20428, b: 0.005, lo: 0, hi: 1 }, 2: { a: 0.05648, b: 0.0075, lo: 0, hi: 1 }, 3: { a: 0.01423, b: 0.008, lo: 0.25, hi: 1.25 }, 4: { a: -0.36761, b: 0.0105, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4218, innerWire: 0.3437, K: 18774.0, n: 319, sMult: 1.014, lineByCount: { 1: { a: 0.11033, b: 0.0065, lo: 0, hi: 1 }, 3: { a: 0.09035, b: 0.007, lo: 0.25, hi: 1.25 }, 4: { a: 1.37367, b: -0.0175, lo: 0.25, hi: 1.25 } }, splitByCount: { 2: { from: 58, below: { a: 0.08797, b: 0.007, a2: -0.03042, b2: 0.02, lo: 0, mid: 1.25, hi: 1 }, above: { a: -0.99091, b: 0.017, a2: -0.02217, b2: 0.0085, lo: 0.25, mid: 0, hi: 1.25 } } } },
            { outerWire: 0.4305, innerWire: 0.3437, K: 19691.7, n: 165, sMult: 0.9985, byCount: { 4: [{ upTo: 1, bonus: 1.25 }] }, lineByCount: { 1: { a: 0.08883, b: 0.0065, lo: 0, hi: 1 }, 2: { a: 0.05997, b: 0.0065, lo: 0, hi: 1 }, 3: { a: 0.10496, b: 0.0065, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4305, innerWire: 0.3625, K: 22248.9, n: 47, sMult: 1.0405, twoOffset: 0.25, byCount: { 4: [{ upTo: 1, bonus: 1.25 }] }, lineByCount: { 1: { a: -0.13123, b: 0.013, lo: 0, hi: 1 }, 2: { a: 0.25588, b: 0, lo: 0.25, hi: 1.25 }, 3: { a: -4.31401, b: 0.0635, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4375, innerWire: 0.3625, K: 23276.7, n: 157, sMult: 1.02725, twoOffset: 0.25, lineByCount: { 1: { a: -0.00492, b: 0.008, lo: 0, hi: 1 }, 2: { a: -0.65692, b: 0.02, a2: -0.02606, b2: 0.009, lo: 0.25, mid: 0, hi: 1.25 }, 3: { a: -0.44922, b: 0.013, lo: 0.25, hi: 1.25 }, 4: { a: -0.06309, b: 0.0065, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4531, innerWire: 0.3625, K: 25580.0, n: 114, sMult: 1.004, byCount: { 4: [{ upTo: 1, bonus: 1.25 }] }, lineByCount: { 1: { a: 0.01223, b: 0.0095, lo: 0, hi: 1 }, 2: { a: -0.04558, b: 0.011, lo: 0, hi: 1 }, 3: { a: -0.22162, b: 0.013, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4531, innerWire: 0.375, K: 27589.4, n: 17, sMult: 1.03275, twoOffset: 0.25, lineByCount: { 2: { a: -2.67504, b: 0.069, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.4615, innerWire: 0.375, K: 29026.7, n: 102, sMult: 1.01825, twoOffset: 0.25, byCount: { 2: [{ upTo: 0.544, bonus: 0.25 }, { upTo: 0.802, bonus: 1.25 }, { upTo: 1, bonus: 0 }], 3: [{ upTo: 0.217, bonus: 0.25 }, { upTo: 0.48, bonus: -0.75 }, { upTo: 0.78, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] }, lineByCount: { 1: { a: -0.13448, b: 0.0145, lo: 0, hi: 1 } } },
            { outerWire: 0.4687, innerWire: 0.375, K: 30214.9, n: 61, sMult: 1.0055, byCount: { 4: [{ upTo: 1, bonus: 0.25 }] }, lineByCount: { 1: { a: -0.1827, b: 0.014, lo: 0, hi: 1 }, 2: { a: -2.81915, b: 0.03, lo: -1, hi: 0 }, 3: { a: -1.97093, b: 0.0225, lo: -0.75, hi: 0.25 } } },
            { outerWire: 0.4687, innerWire: 0.3938, K: 33619.3, n: 10 },
            { outerWire: 0.49, innerWire: 0.3938, K: 38052.1, n: 168, sMult: 1.00875, lineByCount: { 1: { a: -0.20822, b: 0.0125, lo: 0, hi: 1 }, 2: { a: -0.15427, b: 0.011, a2: -0.04196, b2: 0.01, lo: 0, mid: 1.25, hi: 1 }, 3: { a: -5.01084, b: 0.071, lo: 0.25, hi: 1.25 }, 4: { a: -0.74553, b: 0.019, lo: 0.25, hi: 1.25 } } },
            { outerWire: 0.5, innerWire: 0.3938, K: 38403.3, n: 62, sMult: 0.99575, byCount: { 3: [{ upTo: 1, bonus: 0.25 }] }, lineByCount: { 1: { a: -0.19169, b: 0.0135, lo: 0, hi: 1 }, 2: { a: 0.39762, b: 0, lo: 0, hi: 1 } } },
            { outerWire: 0.5, innerWire: 0.4062, K: 42982.9, n: 89, sMult: 1.01925, byCount: { 4: [{ upTo: 1, bonus: 0.25 }] }, lineByCount: { 1: { a: -0.47962, b: 0.019, lo: 0, hi: 1 } }, splitByCount: { 2: { from: 47, below: { a: 0.40425, b: 0, cuts: [0.79431], levels: [0, 1.25, 1] }, above: { a: -2.8812, b: 0.0405, a2: 0.04793, b2: 0.008, lo: 0.25, mid: 0, hi: 1.25 } } } },
            { outerWire: 0.5312, innerWire: 0.4062, K: 44705.9, n: 38, sMult: 0.9745, byCount: { 4: [{ upTo: 1, bonus: 0.25 }] }, lineByCount: { 1: { a: -0.68208, b: 0.0205, lo: 0, hi: 1 } } },
            { outerWire: 0.5312, innerWire: 0.4218, K: 53777.7, n: 56, sMult: 0.99725, lineByCount: { 1: { a: -0.77046, b: 0.0145, lo: 0, hi: 1 }, 2: { a: -0.43756, b: 0.011, lo: 0, hi: 1 } } },
            { outerWire: 0.5312, innerWire: 0.4305, K: 57529.5, n: 54, sMult: 1.01275, byCount: { 3: [{ upTo: 1, bonus: 0.25 }] }, lineByCount: { 1: { a: -1.02733, b: 0.013, lo: 0, hi: 1 }, 2: { a: -0.82055, b: 0.0185, a2: 0.49366, b2: 0, lo: 0, mid: 1.25, hi: 1 } } },
            { outerWire: 0.5625, innerWire: 0.4305, K: 59149.7, n: 11, byCount: { 1: [{ upTo: 1, bonus: -1 }] }, lineByCount: { 2: { a: 4.08033, b: -0.0575, lo: -1, hi: 0 } } },
            { outerWire: 0.5625, innerWire: 0.4375, K: 64260.8, n: 6, byCount: { 2: [{ upTo: 1, bonus: -1 }] } },
            { outerWire: 0.5625, innerWire: 0.4531, K: 75203.6, n: 24, byCount: { 1: [{ upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.625, innerWire: 0.4531, K: 76188.5, n: 4 },
            { outerWire: 0.625, innerWire: 0.4615, K: 83512.5, n: 14 },
            { outerWire: 0.625, innerWire: 0.4687, K: 90247.1, n: 7 },
            { outerWire: 0.625, innerWire: 0.49, K: 111862.3, n: 23 },
            { outerWire: 0.625, innerWire: 0.5312, K: 140955.9, n: 2 },
        ],
    },
    '2 5/8" inside 5 1/4"': {
        innerId: 2.625,
        outerId: 5.25,
        cSlope: 1.15491, cIntercept: -362.27,
        kSlope: 1.50247, kIntercept: -1221.56,
        defaultTau: 40,
        calibration: [
            // C is pinned to a single value by the 150 and 300 lb readings.
            { outerWire: 0.2625, innerWire: 0.1770, C: 1549.5, tau: 56.0, K: 1043.1 },
            { outerWire: 0.2625, innerWire: 0.1875, C: 1680.4, tau: 43.0, K: 1379.4 },
            { outerWire: 0.2625, innerWire: 0.2000, C: 2029.6, tau: 31.5, K: 1911.4 },
            { outerWire: 0.2625, innerWire: 0.2070, C: 2109.6, tau: 39.5, K: 2249.1 },
            { outerWire: 0.2730, innerWire: 0.2187, C: 2706.1, tau: 44.5, K: 2928.4 },
            { outerWire: 0.2890, innerWire: 0.2343, C: 3768.3, tau: 36.5, K: 4031.1 },
        ],
    },
};

// Raynor and Overhead are offered by the dropdown but the reference returns
// the 2 5/8" inside 5 1/4" numbers for both, spring IDs included. Aliased
// rather than given entries of their own, so there is one place to correct
// when real figures turn up.
// NOT REACHABLE, AND KNOWN TO BE WRONG. Kept only because the regression suite
// and dev/price-parity.sh still drive these code paths by setting state directly.
//
// The dropdown offers `3 3/4" inside 6"` alone - see the note in
// static/src/xml/spring_engineering.xml and CLAUDE.md. These two aliases asserted
// that a Raynor 3 1/2" inside 5 1/2" is engineered as a 2 5/8" inside 5 1/4", and
// the reference says otherwise: on the same door it returns 0.25/0.207 for the
// Raynor pair against 0.2625/0.1875 for the pair it was aliased to, at 15" rather
// than the 17" this model produced. Every one of the 8,464 readings behind the
// calibration is the one pair, so nothing here was ever fitted for the others.
//
// DO NOT RE-OFFER A PAIR BY DELETING THIS COMMENT. Calibrating one took thousands
// of reference readings.
const DUPLEX_ALIASES = {
    '3 1/2" inside 5 1/2" (Raynor)': '2 5/8" inside 5 1/4"',
    '3 3/8" inside 5 7/8" (Overhead)': '2 5/8" inside 5 1/4"',
};

// How K scales with spring count.
//
// There is only ONE of these now. There used to be a single constant serving
// both the length and the torque, then two; the length one is gone because
// the length no longer has a fitted scale at all - the catalog formula has
// spring count entering exactly linearly, and the 1- and 2-spring readings
// confirm it to 0.04%. The 0.99 that used to sit there came from a 4-spring
// length figure in a comment, and that comment's arithmetic no longer
// reproduces.
//
// TORQUE is exact and not fitted either: the springs share the door between
// them, so each carries weight * rEff / springs. Exponent 1, by definition.
// It is written as a constant only so the one place it is applied is named.
const DUPLEX_TORQUE_COUNT_EXPONENT = 1;

// How far BELOW the cycle target the reference will still accept a pairing.
//
// NOW 1.0, PINNED BY THE CYCLE COUNT RATHER THAN BY WIRE CHOICE. This was
// 0.95, chosen to offset an error in K. It cannot be pinned the way it was:
// the fraction and K trade off almost exactly, because K is re-derived from
// the same switch points the fraction appears in, so wire and length accuracy
// barely move with it - 2665, 2662 and 2665 corpus readings at 0.95, 0.98 and
// 1.00.
//
// The CYCLE COUNT does move, and it is an output the reference reports, so it
// is what settles the question. Against 2800 readings where the wire agrees:
//
//   fraction   exact (same 1000)   within one step   median error
//     0.90           17.8%              48.0%           -8.91%
//     0.95           47.6%              65.2%           -3.23%
//     0.98           55.6%              83.9%            0.00%
//     1.00           47.0%              99.3%           +0.34%
//
// At 1.00 the fifth percentile is 0.00%: we never compute FEWER cycles than
// the reference, and 99.3% of readings agree to within one rounding step. The
// old 0.95 ran the count 3.2% low across the board, which is also what made
// the new cycles-low warning fire on readings the reference passes.
//
// WHAT 1.0 DOES NOT EXPLAIN is why the reference prints "cycle life
// calculation of 9,000.00 is less than the 10,000 cycle minimum" on 190
// readings - it does sometimes keep a pairing that misses the target, and
// warn. That is the known gap below, not a reason to move the fraction: the
// fraction is what the SELECTION uses, and 0.90 was a reading of the warning
// rather than of the selection.
//
// It does not require the target outright, which the source comments have
// noted since the first commit without pinning. Two rejection boundaries pin
// it: at 685 lb it keeps 0.283/0.2343 at 9,000 cycles with a warning and steps
// up at 690, and at 725 lb it keeps 0.289/0.2343 at 9,000 and steps up at 730.
// Both boundaries sit at 9,000 against a 10,000 target, so the reference's own
// fraction is 0.90.
//
// Confirmed a third way without using any constant from this file: 620 lb
// measures 14,000 cycles on 0.283/0.2253, and 14,000 / (680/620)^4.67 = 9,000,
// so at 680 lb that rung reaches the boundary - which is exactly where the
// reference steps off it.
//
// 0.95 IS USED HERE, NOT 0.90, and the gap is this model's own error rather
// than a disagreement. Scored over 43 readings:
//
//     f = 1.00   35/43      f = 0.93   40/43
//     f = 0.98   40/43      f = 0.90   36/43
//     f = 0.95   42/43      f = 0.85   30/43
//
// K carries about 1% from the reference rounding its cycle counts to the
// nearest thousand, and a 1% error in K is ~5% in the cycle count, which is
// the whole distance between 0.90 and 0.95. So 0.95 against this model's
// cycles is the same decision as 0.90 against the reference's.
//
// RE-SCANNED against the full 45-reading corpus, and 0.95 is a genuine peak
// rather than an edge:
//
//     1.00  37/45      0.96  43/45      0.93  42/45
//     0.98  42/45      0.95  44/45      0.90  38/45
//     0.97  41/45
//
// ONE READING DISAGREES WITH THE FRACTION ITSELF, and it is the last wire miss
// in the corpus. At 675 lb, 1 spring, 9'0" the reference uses 0.3625/0.295
// where this model takes the softer 0.3625/0.289. That rung's K comes from a
// 470 lb reading measuring 53,000 cycles, and scaling by the cycle law alone -
// 53,000 / (675/470)^4.67 - gives 9,775 at 675 lb. So by the reference's own
// arithmetic the softer rung clears 9,000, and the reference still stepped off
// it. Two readings elsewhere show it ACCEPTING exactly 9,000.
//
// So the acceptance rule is not a pure fraction of the target. One reading is
// not enough to say what it is instead, and a threshold tuned to catch this
// case costs more elsewhere - 0.98 drops the corpus to 42/45.
//
// THIS ONLY WORKS BECAUSE K IS NOW MEASURED. With the old fitted K a looser
// threshold made things worse, not better - 15/27 at f = 1.00 falling to 11/27
// at f = 0.90 - because a lower bar lets more rungs qualify and so amplifies
// every error in K. The strict threshold was compensating for bad K.
const DUPLEX_ACCEPT_FRACTION = 1.0;

// Below this fraction of the target the reference calls the cycle life short
// and says so. Measured from 3,070 readings that report their own count: the
// 190 warned ones top out at a ratio of 0.9000 and the 2,880 quiet ones start
// at 0.9600, with nothing in between. Distinct from the accept fraction above,
// which governs SELECTION rather than the warning.
const DUPLEX_WARN_FRACTION = 0.95;

// Bounds on the outer/inner stress ratio of a pairing - see
// duplexPairBalanced. Measured range is 0.862 to 1.040 over thirteen
// pairings; these carry a little margin beyond it.
const DUPLEX_BALANCE_MIN = 0.84;
const DUPLEX_BALANCE_MAX = 1.06;

// The reference prints duplex cycle counts to the nearest thousand.
const DUPLEX_CYCLE_ROUNDING = 1000;


// --- THE CYCLE-RATING CAP: REMOVED ---------------------------------------
// There used to be a DUPLEX_CATALOGUE here - a four-row table capping the
// stiffest pairing on offer per cycle target, on the theory that torsion
// springs are sold by cycle rating so the target picks which catalogue is
// available.
//
// IT WAS WRONG, and measurement said so: a 470 lb 1-spring sweep has the
// reference using 0.3625/0.289, S = 8723, at a 50,000 target, where the table
// said 50,000 topped out at S = 5920. S depends only on the two wire sizes, so
// a product catalogue cannot depend on spring count - yet the per-count
// scaling was the only thing making that reading reachable at all, and at 2
// springs the cap made the reference's own answer impossible.
//
// IT COULD NOT BE REMOVED UNTIL K WAS MEASURED. With the old fitted K,
// deleting it made the wire choice WORSE - 8/11 against 9/11 - because it was
// trimming the ladder to hide rungs that bad K values wrongly accepted. With K
// derived from the reference's own cycle counts it makes no difference at all,
// 26/27 either way, so the compensation is no longer needed and a construct
// known to be wrong is gone.
//
// One of three errors that were fitted against each other. The other two - the
// strict accept-the-target threshold and the pessimistic kSlope line - are gone
// for the same reason: K was the one underneath.

// THE LENGTH RULE. Six reference-API readings (2026-10-01) settle this, and
// the answer is that there was never a rule to fit: the length is the
// catalog's own formula, the same one the Single path already uses and that
// path is known good.
//
//     activeLength = springs x (divider_outer + divider_inner) / TIPPT
//     inner length = round(activeLength)
//     outer length = inner + 1
//
// with divider = 30e6 * wire^5 / (TORSION_CONSTANT * (ID + wire)), exactly as
// the `divider` getter computes it for one spring. The two springs are
// coaxial and wound together, so they share ONE active length and their RATES
// ADD - which is why the sum of the two dividers is the quantity that
// appears, and why spring count enters exactly linearly.
//
// NO FITTED CONSTANTS AT ALL. Five of the six readings come out exact:
//
//     470 lb  7'0"  1 spring              18.005 -> 18   reference 18
//     585 lb  7'0"  2 springs             13.398 -> 13   reference 13
//     620 lb  7'0"  2 springs             14.182 -> 14   reference 14
//     675 lb  9'0"  1 spring              28.167 -> 28   reference 28
//     470 lb  7'0"  1 spring, t 25,000    24.359 -> 24   reference 24
//
// WHAT THIS REPLACES, and why all of it had to go:
//
//   C      a fitted constant per wire combination. It sits 2-6% above the
//          physical divider sum, and not by a constant factor, so it could
//          not be scaled away. It was fitted as the MIDPOINT of a bracket an
//          inch wide, which is why it was never better than about 1% - and a
//          1% error in C moved 22.7% of lengths by a whole inch.
//
//   tau    a regime threshold per combination, compared against C/TIPPT. That
//          quantity moves with the DRUM: the D525-216's rEff is 28% above the
//          D400s', so its x ran ~28% lower and landed in the floor regime 92%
//          of the time against the D400s' 56%. tau was fitted where x
//          happened to sit on the D400-144, which is exactly why no other
//          drum ever came out right.
//
//   0.25"  a quarter inch added whenever x >= tau. Of the six readings, five
//          return a whole inch and the sixth is the out-of-range case below.
//          Its only evidence was a comment whose own arithmetic no longer
//          reproduces.
//
// THE ONE READING THIS DOES NOT REPRODUCE is 200 lb at 7'0", returned as
// 36.25" where this gives 34.875 -> 35. That reading is also the only one the
// reference itself rejects ("cycle life calculation of 1,165,000.00 exceeds
// the 350,000 cycle maximum"), the only one with a fractional length, and the
// only one where the reference contradicts ITSELF: inverting its own reported
// cycle count gives a body of 34.773, which agrees with this formula to 0.3%
// while it prints 36.25. So it is a separate out-of-range path, and fitting
// the main rule to it is what produced tau in the first place.
//
// STILL OPEN: round() against floor(). Every confirmed reading has a
// fractional part below 0.5, so both reproduce all five. One reading whose
// active length lands above x.5 settles it - see dev/worklist.mjs.
//
// THERE IS A LENGTH CEILING, found by a 470 lb 1-spring target sweep that ran
// the same door from 10,000 to 200,000 cycles. The formula is exact at every
// length up to 34" and then drifts:
//
//     target    pairing          active    reference
//      10,000   0.3195/0.2625    18.007       18      ok
//      25,000   0.3437/0.273     24.362       24      ok
//      50,000   0.3625/0.289     31.886       32      ok
//      75,000   0.375/0.3065     39.350       40      MISS  +0.65
//     100,000   0.3938/0.3065    46.187       45      MISS  -1.19
//     150,000   0.3938/0.3195    49.440       50      MISS  +0.56
//     200,000   0.4062/0.331     58.052       59      MISS  +0.95
//
// THE "LONG SPRING" FRAMING WAS WRONG, and a later reading settled it. Ordered
// by active length the remaining failures run 30.66, 34.87 and 46.19 while
// 31.89 and 33.94 pass, so breakage is not a function of length. Three of the
// four cases above were simply rungs that add a whole inch BELOW frac 0.5,
// which round() floors; a ceil-side threshold fixes them and they now
// reproduce. See the note on regimes further down.
//
// WHAT IS ACTUALLY LEFT is three readings needing a bonus the three regimes
// cannot express:
//
//     +2.25   348 lb 3-spring LHR (active 30.659 -> 32.25)
//     +2.25   200 lb 2-spring     (active 34.871 -> 36.25)
//      -1     470 lb 1-spring t100,000 (active 46.182 -> 45)
//
// The two +2.25 cases are both on the softest rung and both over the
// reference's own 350,000 cycle maximum, which it returns as an error. That
// may be the pattern or may be coincidence - two readings cannot say. The -1
// case has the reference ACCEPTING a 2.6% rate error, reporting 45" where the
// required rate demands 46.19", and its own spring weights confirm the 45".
//
// A third over-maximum reading on a different rung would settle whether the
// +2.25 belongs to that regime.
//
// --- THE QUARTER INCH: STRUCTURE FOUND, CALIBRATION MISSING ---------------
//
// Two dense 9-point weight sweeps, each holding one pairing and stepping 5 lb
// at a time, settle what the quarter inch IS without yet making it usable.
//
// It is NOT pairing-specific, which was the standing hypothesis: 575 lb
// returns 14.25" on 0.273/0.2253, not just on the softest rung.
//
// Both sweeps show the SAME three-regime structure as frac(active) falls:
//
//     frac >= tHi        ->  floor(active) + 1
//     tLo <= frac < tHi  ->  floor(active) + 1.25
//     frac <  tLo        ->  floor(active)
//
// With thresholds per pairing it reproduces all 18 sweep readings exactly:
//
//     0.2625/0.2253    tLo 0.002   tHi 0.530    9/9
//     0.273/0.2253     tLo 0.514   tHi 0.634    9/9
//
// NO SINGLE THRESHOLD PAIR CAN SERVE BOTH, and that is a proof, not a failed
// search: sweep 1 needs frac 0.158-0.529 to give +1.25 where sweep 2 needs
// frac 0.169-0.513 to give +0.00. Overlapping ranges, opposite answers. So
// the length rule really does carry a per-pairing parameter - TWO of them.
//
// Which means the original instinct behind C and tau was RIGHT: this rule
// needs per-combination constants. What was wrong was having ONE threshold
// instead of two, and applying it to a fitted C/TIPPT rather than to the
// physical active length, which is what made it move with the drum.
//
// WHY round() IS STILL WHAT SHIPS. The best SHARED thresholds (0.286, 0.634)
// give 15/18 on the sweeps but only 7/10 on the other readings under 40",
// against round(active)'s 9/10. Shipping the structure without per-pairing
// calibration makes every uncalibrated pairing worse, and only 2 of the 12+
// known pairings have a dense sweep. Each one needs roughly 9 readings to pin
// its two thresholds.
//
// So: round(active) is the general rule, exact on 9 of 10 readings under 40"
// whose pairing was never swept. The three-regime form above is what a
// calibrated version would use, and dev/corpus.json holds the readings it was
// derived from.
//
// A THIRD SWEEP (0.289/0.2343, 690-730 lb) is consistent with the structure
// but could not pin it - the +1.25 band sits at 677-688 lb and the sweep
// started at 690. It does show that BOTH thresholds rise monotonically with
// pairing stiffness:
//
//     0.2625/0.2253   S 2030   tLo (0.001,0.158]   tHi (0.529,0.673]
//     0.273/0.2253    S 2281   tLo (0.513,0.634]   tHi (0.634,0.749]
//     0.289/0.2343    S 2928   tLo (0.582,1.000]   tHi (0.000,0.877]
//
// which looks like a phase advancing with S rather than free constants per
// pairing. If that holds, the whole family is two global parameters instead of
// two per pairing - but three points, one of them barely constrained, cannot
// settle it. 680 lb and 685 lb on this pairing are predicted to return 15.25"
// and would both pin this pairing and test the phase idea.
function duplexActiveLength(pair, step, springs, tippt) {
    if (!pair || !step || !tippt || !springs) {
        return 0;
    }

    const divider = (wire, id) =>
        (30000000 * Math.pow(wire, 5)) / (TORSION_CONSTANT * (id + wire));

    // sMult IS THE RUNG'S MEASURED STIFFNESS, against the computed one.
    //
    // The reference reports both its length and its TIPPT, and the formula is
    // length = springs * S / TIPPT, so S can be solved from every reading:
    // S = length * TIPPT / springs. Across a rung's readings the computed S is
    // wrong by up to 4.6%, and differently per rung - 0.2625/0.2253 implies
    // 1062 where the dividers give 1015, while 0.3625/0.283 implies 4124
    // against 4217. On a 20" spring 4.6% is nearly an inch, which is precisely
    // the error the length bands were absorbing.
    //
    // One number per rung, fitted from the readings. It is per RUNG and not per
    // spring count because stiffness belongs to the wire pair - and the
    // measurement agrees, per rung generalising better with fewer parameters.
    const stiffness = step.sMult || 1;

    // FROM THE DISPLAYED TIPPT, rounded to one decimal, which is the same rule
    // the cycle count and the MIP warning already follow: the reference
    // computes from the figures it shows. Using the exact value instead cost
    // ten points on the external samples - 66.2% against 76.3% - because the
    // length sits on a grid and a tiny TIPPT difference flips the snap.
    const shown = Math.round(tippt * 10) / 10;

    // END COILS BELONG HERE AND THE COUPLING IS NOT SOLVED, so they are left
    // out. Measured, reverted, and worth the note because the physics is not in
    // doubt - only how the two springs share the shaft.
    //
    // A spring's rate uses its ACTIVE coils; the coils seated in the cone do not
    // flex. The catalogue states the rest itself: "COIL NUMBER x WIRE SIZE =
    // SPRING LENGTH", and its worked example - a .250 wire, 2" ID, 32" spring at
    // "IPPT is 41.5 per spring" - implies 4.96 dead coils, i.e. 5. Our formula
    // with 5 reproduces that at 41.51, and reproduces six rows of the published
    // 2" ID rate table to better than 0.17%.
    //
    // The dead-coil count by ID is settled too, fitted from 479 single-spring
    // readings: 5 at 1.75", 2.625", 3.75" and 4.375"; 3 at 5.25" and 6". Which is
    // exactly LARGE_ID_THRESHOLD and the two END_COILS constants, and the Single
    // path has always applied them - it predicts length to 0.073".
    //
    // SO WHY NOT HERE. Two nested springs turn together, so their rates should
    // add, each over its own active length, with the wound lengths an inch apart.
    // Written that way the predicted TIPPT is unbiased - +0.69% against -3.39%
    // without the end coils - but its SPREAD does not improve, 2.78% against
    // 2.52%, which says the rates do not simply add. Shipped on the strength of
    // the holdout (+26 readings) and then withdrawn: in sample it cost 121
    // readings, 82 fixed against 203 broken, concentrated on the highest-traffic
    // rung, and the never-tuned draws moved 2.8 points in opposite directions for
    // a paired net of -2 at p = 0.774. Re-tuning LINE_SLACK does not recover it,
    // so the band knobs were not the confound.
    //
    // sMult absorbs the difference instead, which is why it is 1.18% off 1.000 on
    // average and correlates with the outer spring's share of the divider sum.
    // Whatever the real coupling is, finding it is the one lead left that could
    // move accuracy by more than noise - see dev/README.md.
    return (
        (springs *
            stiffness *
            (divider(step.outerWire, pair.outerId) +
                divider(step.innerWire, pair.innerId))) /
        shown
    );
}

// THE THREE-REGIME ROUNDING, where a rung has been swept densely enough to
// know its two thresholds.
//
//     frac >= tHi        ->  floor(active) + 1
//     tLo <= frac < tHi  ->  floor(active) + 1.25      (the quarter inch)
//     frac <  tLo        ->  floor(active)
//
// Three 9-point weight sweeps, each holding one rung and stepping 5 lb, fit
// this exactly - 9 of 9 on every one of them - where plain round(active) gets
// 30 of 39 across all readings and this gets 37.
//
// THE THRESHOLDS ARE PER RUNG and that is measured, not assumed. Sweep 1 needs
// frac 0.158-0.529 to give +1.25 while sweep 2 needs frac 0.169-0.513 to give
// +0.00 - overlapping ranges, opposite answers - so no single pair of
// thresholds can serve both. Both rise with rung stiffness, which hints they
// are a phase rather than free constants, but three rungs cannot settle that.
//
// WITHOUT THRESHOLDS IT FALLS BACK TO round(active).
//
// WHICH RUNGS GET THEM, AND ON WHAT EVIDENCE. A rung is given thresholds only
// where round(active) is PROVABLY wrong on a reading - that is, where a
// reading floors at frac above 0.5 (round would have gone up), or shows the
// quarter inch at all (round can never produce it). Everywhere else round is
// left alone, and it is exact on every such reading under 40".
//
// Two kinds of evidence, and the second is weaker:
//
//   BRACKETED - readings on both sides, so tLo and tHi are both pinned. The
//   three rungs with a 9-point sweep are here, each reproducing 9 of 9.
//
//   ONE-SIDED, FLOOR - only floor readings, so all that is known is that tLo
//   lies above the highest frac seen flooring. tLo is set just above it and
//   tHi equal to it, which asserts NO quarter band rather than inventing one.
//
//   ONE-SIDED, CEIL - the mirror case. Some rungs are seen adding a whole inch
//   at a frac BELOW 0.5, which round() gets wrong by flooring. There tLo is set
//   to 0.002, so everything ceils except an active length that is already a
//   whole number. 0.375/0.3065 is the clearest: two readings, frac 0.350 and
//   0.940, both +1, and round only gets the second.
//
// Either way the change is confined to the frac range the readings cover, and
// the `n` on each entry says how many stand behind it - n=1 means exactly that.
//
// THE MODEL IS LOCALLY VALID, NOT CORRECT, and one reading proves it. On
// 0.273/0.2253:
//
//     580 lb   active 13.513   frac 0.513   reference bonus +0.00
//     286 lb   active 27.404   frac 0.404   reference bonus +1.25
//
// frac 0.513 requires tLo > 0.513 while frac 0.404 requires tLo <= 0.404, so
// no threshold on frac(active) satisfies both. What separates them is the
// INTEGER part of active, 13 against 27 - and this rung's thresholds were
// fitted on a sweep that never left active 13.5.
//
// It does not always fail that way: the 0.2625/0.2253 thresholds were fitted
// near active 15 and are correct at active 34.020. So frac(active) is a
// coordinate that correlates locally with whatever the reference quantises,
// and transfers sometimes.
//
// The thresholds are kept because they are right on 48 of 49 readings. Closing
// this properly needs a dense sweep at a SECOND integer part of active on the
// same rung, which is a different experiment from the three already done.
//
// RULED OUT, with a designed probe: being over the reference's 350,000 cycle
// maximum does NOT cause the +2.25 bonus. A 205 lb door returns 1,042,000
// cycles and still takes the ordinary +1.25.
//
// The thresholds are genuinely per rung - the fitted values run from 0.000 to
// 0.740 - so one of them cannot be borrowed for another rung. See the proof in
// duplexActiveLength's note that no shared pair can serve two of them.
// THE QUARTER-INCH GRID IS SET BY THE SPRING COUNT, which 116 readings make
// unambiguous:
//
//     1 spring    18 of 18 lengths are a whole inch, none a quarter
//     2 springs   52 whole, 10 quarter - mixed, and the rung rules handle it
//     3 springs   20 of 20 are a quarter, none whole
//     4 springs   16 of 16 are a quarter, none whole
//
// At one spring that is p = 4^-18, so it is not chance. The rung rules below
// were fitted mostly on 1- and 2-spring readings and happily return a whole
// inch at 3 or 4 springs, which is provably the wrong GRID - and measured
// against the reference the error was 0.25 LOW in 11 of the 16 cases where the
// wire was right.
//
// So the grid is enforced: at 3 or more springs a whole-inch answer is lifted
// to the quarter above it. This does not claim to know the full rule - it
// claims to know which values are POSSIBLE, which is weaker and solid.
function duplexSnapToGrid(length, springs) {
    if (!(length > 0) || springs < 3) {
        return length;
    }

    return Math.abs(length - Math.round(length)) < 1e-9 ? length + 0.25 : length;
}

function duplexLength(activeLength, regime, springs) {
    if (!(activeLength > 0)) {
        return 0;
    }

    const whole = Math.floor(activeLength);
    const frac = activeLength - whole;

    // A SECOND REGIME AT LONG ACTIVE LENGTHS on the softest rung, which the
    // bands below cannot express because they are a function of frac alone and
    // this one depends on the active length as well. The boundary is bracketed
    // to (25.290, 25.807] by a 500/490 lb pair.
    //
    // THE SPLIT INSIDE IT IS PER SPRING COUNT, which 24 readings above active
    // 25.5 on this rung make plain:
    //
    //     2 springs   n=11   +1.25 at frac 0.020-0.453, +2.25 at 0.786-0.928
    //                        so the split is in (0.453, 0.786], midpoint 0.620
    //     3 springs   n=13   +2.25 at every frac from 0.110 to 0.905,
    //                        so the split is at or below 0.110
    //
    // A single split of 0.065 was used before this, fitted when the only
    // long 2-spring readings were at frac 0.020 and 0.871. It put six 2-spring
    // doors an inch long. 1 and 4 springs have no readings up here and fall
    // through to the bands below rather than borrow a split.
    const long = regime && regime.long;

    if (long && activeLength >= long.from && long.byCount[springs] !== undefined) {
        return frac < long.byCount[springs]
            ? whole + 1.25
            : whole + long.above;
    }

    // DERIVED BANDS, per rung AND per spring count - see dev/derive.mjs.
    //
    // One rule per rung is not enough: 1, 2, 3 and 4 springs sit on different
    // quarter-inch grids and take different bonus values, so the bonus is a
    // piecewise-constant function of frac for each (rung, count) pair. Bands
    // exist only where readings cover them and only where plain rounding is
    // already wrong; everything else falls through to round().
    // A LINE IN THE INTEGER PART, where one fits. The bonus threshold is not
    // constant in frac: on 0.3625/0.283 at one spring it flips at about 0.80
    // at floor 17, 0.84 at floor 18, 0.91 at floor 24 and never by floor 25.
    // Keying on frac alone cannot express that - frac 0.815 wants +1 at active
    // 17.815 and 0 at active 25.816, same rung and same spring count - and the
    // band fitter answered it by slicing frac into alternating slivers,
    // eighteen of them on 0.375/0.295, which fit the readings and predicted
    // nothing.
    //
    // t = a + b*floor is two parameters and covers 39 of the 41 two-bonus
    // groups. Groups with three or more bonus values keep their bands.
    // A REGIME BOUNDARY, where the group is really two rules rather than one
    // with three levels. On 0.3625/0.283 at one spring the -1 bonus appears at
    // floor 29 and above and never below, and one threshold line fits each
    // side separately. Same shape as the `long` override the softest rung has
    // always carried by hand.
    //
    // Each line owns a disjoint range of floor, so it is constrained locally.
    // That is the difference from two thresholds over the same readings, which
    // had one slope serving every length and cost 13 points of out-of-sample
    // accuracy.
    const split = regime && regime.splitByCount && regime.splitByCount[springs];
    const line = split
        ? (whole >= split.from ? split.above : split.below)
        : regime && regime.lineByCount && regime.lineByCount[springs];

    if (line) {
        const first = line.a + line.b * whole;

        // K PARALLEL THRESHOLDS. The bonus on a rung can take more than two
        // values - four on 0.2625/0.2253 at three and four springs, which is
        // 25% of everywhere a random door lands - and they are lo + k for
        // integer k. One slope, K-1 intercepts, and the bonus is the level
        // whose threshold the fraction has passed.
        if (line.cuts) {
            let level = 0;

            if (frac > first) {
                level = 1;

                for (let i = 0; i < line.cuts.length; i++) {
                    if (frac > line.cuts[i] + line.b * whole) {
                        level = i + 2;
                    }
                }
            }

            return whole + line.levels[Math.min(level, line.levels.length - 1)];
        }

        // TWO PARALLEL THRESHOLDS where the bonus has three levels. They
        // share the slope and differ only in intercept, so the third level
        // costs one number rather than a second line. 0.3625/0.283 at one
        // spring is the clearest case: its bonus runs -1, 0 and +1, and a
        // single threshold cannot place all three.
        if (line.mid !== undefined) {
            // b2 ONLY WHERE IT WAS MEASURED. Thresholds normally share a
            // slope; on 0.2625/0.2253 at two springs they visibly do not -
            // the lower boundary climbs about 0.04 per inch of floor while
            // the upper one sits flat near 0.75 - so that group carries its
            // own second slope and every other group falls back to the first.
            const second = line.a2 + (line.b2 ?? line.b) * whole;

            return whole + (
                frac > second ? line.hi : frac > first ? line.mid : line.lo
            );
        }

        return whole + (frac > first ? line.hi : line.lo);
    }

    const bands = regime && regime.byCount && regime.byCount[springs];

    if (bands) {
        for (const band of bands) {
            if (frac < band.upTo) {
                return whole + band.bonus;
            }
        }
    }

    // THE MEASURED GRID, not plain rounding. The reference's inner spring is a
    // whole number of inches at 1 spring (1843 of 1843 readings), whole plus a
    // quarter at 3 and 4 springs (594 and 413 of each), and at 2 springs it is
    // one or the other - 793 at .0 and 274 at .25, and never .5 or .75. So two
    // springs takes whichever of {N, N+0.25} is nearer, which is deterministic.
    if (springs === 1) {
        return Math.round(activeLength);
    }

    if (springs >= 3) {
        return Math.round(activeLength - 0.25) + 0.25;
    }

    // TWO SPRINGS TAKES ITS OFFSET FROM THE RUNG. It lands on .0 for 799 of
    // the readings and .25 for 276, never .5 or .75, and the rung alone
    // predicts which on 86.4% of them. Snapping to whichever was nearer
    // instead was the biggest single source of error on the doors the
    // reference answers without complaint.
    const off = (regime && regime.twoOffset) || 0;

    return Math.round(activeLength - off) + off;
}

// --- Drum limits and warnings --------------------------------------------
// The calculator still computes past these; it flags the result rather than
// refusing. Yellow means the inputs exceed what the drum is rated for, red
// (not yet implemented) means the design itself is unsafe.
//
// maxHeight is the nameplate figure - the trailing number in each drum's name
// is its rating in inches - not the catalog's cable capacity, which runs a
// little higher (98, 148 and 231 for these three).
//
// maxWeight is the whole DOOR, which is twice the catalog's "max load per
// drum" because a door hangs on two: 265, 375 and 750 lb per drum become
// 530, 750 and 1500 here.
//
// maxCable is carried for completeness and is NOT yet checked - the app has
// no cable-size input to compare it against.
const DRUM_LIMITS = {
    // FROM THE REFERENCE'S OWN DRUM RECORD, not from the nameplate in the name.
    // GET /spring-engineering/drum?drumName=... returns the drum, and the
    // D525-216 carries maximumHeight 231 - fifteen inches more than its name
    // suggests. Confirmed against the calculator: the multiplier still moves at
    // 228 and 231 and freezes at 0.202291 from 234, where the over-height
    // warning starts. Capping at 216 shortened the spring on any door between
    // 217 and 231 inches, which the reference handles perfectly well.
    //
    // D400-96 and D400-144 do match their names, at 96 and 144.
    "CANIMEX/TF D400-96": { maxHeight: 96, maxWeight: 530, maxCable: '1/8"' },
    "CANIMEX/TF D400-144": { maxHeight: 144, maxWeight: 750, maxCable: '5/32"' },
    "CANIMEX/TF D525-216": { maxHeight: 231, maxWeight: 1500, maxCable: '3/16"' },
};

// --- Wire size limits per spring ID ---------------------------------------
// The band of wire a given inside diameter can actually be wound with. Both
// bounds are inclusive - a wire exactly on the limit passes, only one past it
// is flagged.
//
// The display strings are the reference calculator's own, trailing zero and
// all, which is why 2 5/8"'s minimum reads 0.1770" in the message where the
// Wire Size dropdown spells the same size 0.177". Kept verbatim rather than
// normalised so the two calculators can be read side by side.
//
// Only the three Single IDs are covered. The Duplex pairs have no published
// band yet, so they raise nothing rather than borrowing a neighbour's.
const WIRE_LIMITS = {
    '2 5/8"': {
        min: 0.177,  minText: '0.1770"',
        max: 0.331,  maxText: '0.331"',
    },
    '3 3/4"': {
        min: 0.2253, minText: '0.2253"',
        max: 0.4062, maxText: '0.4062"',
    },
    '5 1/4"': {
        min: 0.2625, minText: '0.2625"',
        max: 0.4375, maxText: '0.4375"',
    },
};

// WIRE_LIMITS again, keyed by NUMERIC inside diameter. The Duplex path knows
// its pair's diameters as numbers, not as the dropdown's strings, so it
// cannot look into the table above directly. Derived from it rather than
// retyped, so the two can never disagree.
// --- Duplex limits the reference enforces --------------------------------
// All three read straight off the reference's own messages, which the pulled
// batches carry. They are the Duplex half of the warning system, which had
// none of this: Duplex raised five warnings where the reference raises eleven.
//
//   "Assembly MIP (2048.1900) is over max MIP (2000 - Exceeds cone capacity"
//   "Wire size exceeds 0.4062 maximum for the inner spring inner diameter."
//   "Wire size exceeds 0.4375 maximum for the outer spring inner diameter."
//   "Only spring lengths between 0 and 120" are supported"
//
// MIP is moment-inch-pounds carried by ONE spring at full wind, and the
// formula is exact against 682 readings: (TIPPT / springs) * turns. At one
// spring 305.7 * 6.7 = 2048.19 and at two 602.6 * 6.7 / 2 = 2018.71, both to
// the last digit the reference prints.
const DUPLEX_MAX_MIP = 2000;
const DUPLEX_MAX_SPRING_LENGTH = 120;

// The wire a Duplex spring ID can be wound with AND SOLD. The reference will
// return a stiffer wire than this - it is how the stiff end of the ladder
// works - but it attaches "Service Spring Corporation will not sell springs
// and Canimex style cones" to the answer. Offering the pairing without that
// sentence is how a quote gets built on a spring the supplier declines.
const DUPLEX_WIRE_MAX = { 3.75: 0.4062, 6: 0.4375 };

const WIRE_LIMITS_BY_ID = Object.fromEntries(
    Object.entries(WIRE_LIMITS).map(([text, band]) => {
        const value = text.replace('"', "").trim();

        if (!value.includes(" ")) {
            return [Number(value), band];
        }

        const [whole, fraction] = value.split(" ");
        const [numerator, denominator] = fraction.split("/");

        return [Number(whole) + Number(numerator) / Number(denominator), band];
    })
);

// The published wire band for an inside diameter, or null where there is
// none. NULL MEANS UNKNOWN, not unlimited - callers must not read a missing
// band as permission.
function wireBandForId(id) {
    return WIRE_LIMITS_BY_ID[id] || null;
}

// Whether a duplex pair can actually be BUILT from these two wires. Two
// independent questions, and both were being missed:
//
//   GEOMETRY   the inner spring plus two wire diameters has to fit inside the
//              outer spring's ID. This was already checked, but only on
//              generated combinations.
//
//   WINDING    each wire has to lie inside its own spring ID's band. This was
//              not checked at all on the Duplex path, and it is why the
//              2 5/8" inside 5 1/4" pair was offering an inner wire of
//              0.3437" and up against a published 0.331" ceiling - 621
//              candidate pairs reaching a 0.625" wire on a 2.625" spring.
//              The 6" outer has no published band, so it constrains nothing
//              and the pair is judged on its inner alone.
//
// Applied to MEASURED combinations too. A measured pair that failed either
// test would mean the table and the reading disagree, which is worth seeing
// rather than silently allowing - none currently does.
// Peak stress in one spring of the pair, up to a factor the two share.
//
// Both springs have the same active length and turn through the same angle,
// so each carries torque = (divider / L) * turns and the stress that follows
// is torque / wire^3. Substituting the divider:
//
//     stress  ~  wire^5 / ((ID + wire) * wire^3)  =  wire^2 / (ID + wire)
//
// the (turns / L) and the elastic constants being common to both and so
// irrelevant to their RATIO. That ratio is the whole point - see
// duplexPairBalanced.
function duplexSpringStress(wire, springId) {
    return (wire * wire) / (springId + wire);
}

// Whether the two wires are a pairing the reference would actually offer.
//
// MEASURED, from all thirteen pairings the reference has been seen to use:
// the outer spring is NEVER materially more stressed than the inner. The
// stress ratio outer/inner runs 0.862 to 1.040 across every one of them, and
// for six of the seven inner sizes the stiffest outer used is exactly the
// stiffest the balance allows. The inner is the limiting spring - which is
// also the one whose cycle life the reference reports.
//
// THIS IS WHAT MAKES THE LADDER ONE-DIMENSIONAL. Generating the free cross
// product of the wire table instead was tried and was much worse: it buries
// the real rungs under soft, badly-matched pairings that meet the cycle
// target first, and the wire choice fell from 8 of 11 reference readings to
// 2 of 11. The pairing is a curve through the two wire sizes, not a product
// of them.
//
// The bounds are the measured range with a little margin, not a theory. A
// pairing outside them has never been observed.
function duplexPairBalanced(pair, outerWire, innerWire) {
    const ratio =
        duplexSpringStress(outerWire, pair.outerId) /
        duplexSpringStress(innerWire, pair.innerId);

    return ratio >= DUPLEX_BALANCE_MIN && ratio <= DUPLEX_BALANCE_MAX;
}

// `measured` marks a rung that came from the calibration table, which means
// the reference was OBSERVED using it.
//
// THE PUBLISHED WIRE BAND IS A SINGLE-SPRING BAND AND DOES NOT BIND A DUPLEX
// PAIR. WIRE_LIMITS caps 3 3/4" at 0.4062, and the reference demonstrably
// winds 0.4218, 0.4305 and 0.4615 inner wires on that same 3 3/4" inner
// spring - there are readings on all three. The note on WIRE_LIMITS says the
// Duplex pairs have no published band and should not borrow a neighbour's;
// this function was borrowing one anyway.
//
// The cost was the entire stiff end of the ladder. Four calibrated rungs -
// 0.5312/0.4218, 0.5312/0.4305, 0.5625/0.4305 and 0.625/0.4615 - were built,
// given a K from real readings, and then silently dropped here, so a door
// past 1712 lb had nowhere to step: the softer pair was correctly REJECTED on
// cycle life and then chosen anyway because the list held nothing stiffer.
// Those four rungs were 78 of 108 corpus failures.
//
// The geometric check stays for everything: a pair that cannot physically be
// wound is worse than no suggestion. The band check now applies only to
// GENERATED rungs, where it is the only thing keeping extrapolation inside
// sizes anyone has seen used.
function duplexPairBuildable(pair, outerWire, innerWire, measured = false) {
    if (pair.innerId + 2 * innerWire >= pair.outerId) {
        return false;
    }

    if (measured) {
        return true;
    }

    const inner = wireBandForId(pair.innerId);

    if (inner && (innerWire < inner.min - 1e-9 || innerWire > inner.max + 1e-9)) {
        return false;
    }

    const outer = wireBandForId(pair.outerId);

    if (outer && (outerWire < outer.min - 1e-9 || outerWire > outer.max + 1e-9)) {
        return false;
    }

    return true;
}

// --- Torsion assembly length ----------------------------------------------
// What the assembly measures along the shaft, against the width it has to fit
// inside. Reverse-engineered from two reference readings:
//
//   springs  door width   reference length
//   2        9'0" (108")  115.40103713850469"
//   1        4'0" (48")    48.67261549495042"
//
//   assembly = springs * (springLength + turns * wire) + ASSEMBLY_HARDWARE[springs]
//
// Three pieces:
//
//   springLength * springs   The springs themselves. springLength is per
//                            spring and already scales with the count.
//
//   turns * wire             How much each spring's body GROWS as it is
//                            wound. A torsion spring lengthens by one wire
//                            diameter per turn, so a fully wound spring is
//                            longer than the one you ordered - and it is the
//                            wound length that has to fit.
//
//   ASSEMBLY_HARDWARE        Cones, centre bracket, drums and end bearing
//                            plates. FLAT, not per spring. This is the part
//                            the second reading settled: at one spring a
//                            per-spring 12" would have predicted 36.673"
//                            where the reference says 48.673".
//
// Both readings land within 0.0006%, which is the error in the fitted turns
// curve rather than anything structural.
//
// ONE PIECE IS NOT FULLY PINNED. Both readings share a door height, so both
// share a turns value, which means `turns * wire` and a flat 2.2298" per
// spring fit them equally well. turns * wire is the textbook behaviour and
// the numbers agree with it, so that is what is used here - but a reading at
// a different height is what would actually prove it. The two only diverge by
// under 1% of the assembly length, so the warning fires in much the same
// place either way.
// Duplex assembly hardware, MEASURED per spring count.
//
// The reference never reports its assembly length, but it warns when that
// length exceeds the door width - and the width is an input, so sweeping the
// width one inch at a time brackets the length to the inch. Nine brackets
// across 1 to 4 springs (dev/assembly-solve.mjs, dev/pulled-a1.json):
//
//   springs   hardware must lie in   taken
//      1       (15.717, 16.717]      16.25
//      2       (27.928, 28.723]      28.5
//      3       (27.974, 28.974]      28.5
//      4       (31.965, 32.094]      32
//
// It is not flat, which is what the Duplex path assumed by borrowing the
// Single constant of 24. One spring needs no centre bearing bracket; two and
// three share one, at +12.25"; four needs a second, at +3.5". That accounts
// for all four values and for why two and three are identical.
//
// WHY THE OLD 24 SURVIVED SO LONG: it was derived from two SINGLE-path
// readings, and the file already noted that one piece of it was not fully
// pinned because both shared a door height. A Single assembly carries one
// spring per position where Duplex nests two, so there was never a reason for
// the hardware to match - it was simply never measured on Duplex.
//
// The rest of the formula is confirmed, not replaced: solving for the hardware
// with the reference's own length and turns gives a spread of 0.2" across the
// three 2-spring brackets, where dropping the winding term widens it to 1.5".
// MEASURED THE SAME WAY FOR BOTH ASSEMBLIES, because it is the same hardware.
// Single carried a flat 24" fitted from two readings whose inputs were never
// recorded, so it could not be re-solved - and it was wrong at every spring
// count. Sweeping the door width an inch at a time on a Single hi-lift door
// (575-120, 7'0", 60" hi-lift, 2 5/8", 200 lb, dev/pulled-s2.json) brackets
// the reference's own assembly length and solves for the hardware:
//
//   springs   width that warns / does not   hardware must lie in   flat 24 was
//      1              -    /   80            (-inf, 17.29]          too big
//      2             110   /  111            (27.62, 28.62]         too small
//      3             117   /  118            (27.68, 28.68]         too small
//      4             125   /   -             (19.73, +inf)          consistent
//
// Every bracket contains the value already measured for Duplex, so there is
// one table, not two. That is what the physics says too: the hardware is
// cones, the centre bearing bracket, the drums and the end bearing plates,
// none of which care whether the springs on the shaft are nested.
//
// WHAT THE FLAT 24 COST. At 200 lb this door is a 38.25" spring on a 108"
// opening; the reference calls it too long and we did not, because 24 put the
// assembly at 106.27" where 28.5 puts it at 110.88". A missing too-long
// warning is the dangerous direction - it quotes a spring that will not fit
// the opening, and now prices it too.
// REFINED AGAINST EVERY TOO-LONG OBSERVATION, 5,643 of them across both
// assemblies, both lifts and all four counts. The reference warns iff the
// assembly exceeds the width, so each reading is a one-sided bound on the
// hardware, and the two-spring bounds close to (27.91, 28.14]:
//
//   springs   bounds from 5,643 readings   agreement at 28.5   at 28
//      1          inconsistent              2174/2178          same
//      2          (27.91, 28.14]            1533/1544          1544/1544
//      3          (27.95, 28.58]             942/942            942/942
//      4          (31.94, 32.07]             979/979            979/979
//
// 28.5 sat just outside the two-spring window, which is what the eleven
// false too-long warnings were: every one of them overshot by between 0.12"
// and 0.45", a boundary case rather than a wrong model. 28 is inside both the
// two- and three-spring windows, so one value still serves both.
//
// ONE SPRING IS LEFT AT 16.25. Its bounds do not close - some reading wants
// more than 15.71 and another no more than 13.80 - so a single constant
// cannot satisfy them and the residue is a fault somewhere else in the
// one-spring path. 16.25 already agrees on 2,174 of 2,178; the best possible
// constant gets 2,176, which is not worth moving for.
const ASSEMBLY_HARDWARE = { 1: 16.25, 2: 28, 3: 28, 4: 32 };

// The ceiling on the cycle formula itself. Past this the reference stops
// trusting its own answer rather than reporting a larger number, so this is a
// bound on the CALCULATION, not on any spring.
const CYCLE_MAX = 350000;

// The FLOOR on the cycle formula, and it is a constant - not a fraction of
// whatever cycle life was asked for.
//
// This is the "cycle life calculation of N is less than the 10,000 cycle
// minimum" message, and the message means what it says: 10,000 is the lowest
// life the reference will quote at all, and also the lowest target it offers.
// It is not a tolerance on the target. See the warning that uses it for how
// long that took to see.
const CYCLE_MIN = 10000;

// --- Pricing --------------------------------------------------------------
// What the assembly is quoted at. Three parts, kept separate because they are
// charged on different things:
//
//   LABOUR  a flat fee, once per quote however many springs the door takes.
//
//   CONES   per SPRING, chosen by inside diameter. A Duplex spring is two
//           springs nested on one shaft position, so it carries a set for the
//           inner diameter and a set for the outer - the two are added.
//
//   STEEL   per pound of FINISHED spring, counting every spring in the
//           assembly. It is taken from the weights the results already show,
//           which are themselves taken from the quarter-inch length that gets
//           built, so the price always agrees with the figures above it.
// THE COSTS ARE NOT IN THIS FILE, AND THAT IS THE POINT.
//
// `const STEEL_PRICE_PER_LB = 1.46` and the cone price table used to sit here,
// read by the controller out of this source so that one file held the figures.
// Everything under static/ is served to anybody who opens the page, so they were
// in the public bundle - and publishing the costs puts the markup one division
// away from any quote, which undoes the whole reason the percentage is kept off
// the wire.
//
// They are in pricing.py now. This file never used them: prices come from
// /spring-calculator/rates, already marked up. See normaliseRates below.

// The rates as the server sends them, with the cone keys turned into NUMBERS.
//
// JSON object keys are strings, and the two sides do not spell a number the
// same way: this file writes the 6" cone as `6`, which JavaScript keys as "6",
// while the server formats the same float the way Python does, as "6.0". A
// string lookup therefore missed it and the cone was quoted free. Comparing
// numbers cannot drift apart that way, whatever either side does to the text.
function normaliseRates(rates) {
    const cones = new Map();

    for (const [key, price] of Object.entries(rates.cones ?? {})) {
        const diameter = Number(key);

        if (Number.isFinite(diameter)) {
            cones.set(diameter, Number(price));
        }
    }

    return {
        cones,
        perLb: asNumber(rates.perLb),
        labor: asNumber(rates.labor),
        fillerPerFoot: asNumber(rates.fillerPerFoot),
        fillerSpringId: Number(rates.fillerSpringId),
    };
}

// A number, or NaN if there is not one there - THE SAME TRAP AS THE SERVER'S,
// in the other language.
//
// The labour charge is flat and already a selling price, so it is used exactly
// as sent, and zero is a legitimate value for it. That rules out testing whether
// it is truthy, which leaves testing whether it is a number - and JavaScript is
// generous about what it will turn into one. `Number(undefined)` is NaN as you
// would hope, but `Number(null)` and `Number("")` are both 0, so a field the
// server left out as null, or blanked, would arrive as a labour charge of
// nothing and the page would quote the work for free against a cart that
// charges for it.
//
// This is the same shape as `float(False) === 0.0` in controllers/main.py, which
// cost a silent sell-at-cost there. Caught here by the invariant that asks for
// it rather than in production, which is the only difference.
function asNumber(value) {
    if (value === null || value === undefined || String(value).trim() === "") {
        return NaN;
    }

    return Number(value);
}

// Shown once, as its own message, whenever any warning is raised.
const WARNING_NOTE =
    "Use extreme caution when designing springs for use with this drum.";

// The Spring ID each assembly opens on - the FIRST option its dropdown
// offers, which matters because that is what a browser falls back to showing
// when the stored value is not in the new list.
//
// The two lists share no strings: Single offers 3 3/4" where Duplex offers
// 3 3/4" inside 6". So every assembly switch leaves the old value orphaned,
// which is the whole reason the handler below exists.
//
// Triplex is absent on purpose - its Spring ID row is hidden entirely, so
// there is nothing to pick and nothing to measure.
const FIRST_SPRING_ID = {
    Single: '2 5/8"',
    Duplex: '3 3/4" inside 6"',
};

// The starting values, in one place so setup() and the Clear button cannot
// drift apart. Returns a fresh object each time - handing the same one to
// useState twice would let a reset alias the original.
function defaultState() {
    return {
        assembly: "Single",
        springs: 2,
        springId: '2 5/8"',
        cycles: "10,000",
        // Add to Cart: in flight, and the last thing the server said about it.
        cartBusy: false,
        cartError: "",
        liftType: "Standard",
        liftin: "",
        radius: "15",
        drum: "",
        doorWidthFeet: 9,
        doorWidthInches: 0,
        doorHeightFeet: 7,
        doorHeightInches: 0,
        weight: "",
        pitch: false,
        pitchAmount: "0/12",
        wireSize: '0.25"',
        showWarnings: false,
        showDrumInfo: false,
    };
}

export class SpringEngineering extends Component {

    static template = "spring_engineering.Calculator";

    setup() {
        this.state = useState(defaultState());

        // THE RATES COME FROM THE SERVER, BEFORE THE FIRST RENDER. They are the
        // costs below with the markup already applied, so nothing here has to
        // know the markup to show a figure that matches what the cart charges.
        //
        // onWillStart, so a price is never shown at cost by mistake while a
        // fetch is in flight. If it fails the price block says so rather than
        // quoting the wrong number - see priceAvailable.
        onWillStart(async () => {
            try {
                const rates = await rpc("/spring-calculator/rates", {});

                if (rates && !rates.error) {
                    this.rates = normaliseRates(rates);
                }
            } catch {
                this.rates = null;
            }
        });

        // Re-pick the wire whenever anything that feeds torque changes, or
        // the cycle target does. A size chosen by hand therefore survives
        // only until the next such change, which is how the reference
        // behaves. useEffect runs after the render, so it never races the
        // t-model that just wrote the value.
        useEffect(
            () => {
                const wire = this.recommendedWire;

                if (wire !== null) {
                    this.state.wireSize = formatWire(wire);
                }
            },
            () => [
                this.state.weight,
                this.state.springs,
                this.state.drum,
                this.state.liftin,
                this.state.cycles,
            ]
        );
    }

    //start divider

get springIdNumber() {
    const value = this.state.springId.replace('"', '').trim();

    if (value.includes(' ')) {
        const [whole, fraction] = value.split(' ');
        const [numerator, denominator] = fraction.split('/');

        return Number(whole) + Number(numerator) / Number(denominator);
    }

    if (value.includes('/')) {
        const [numerator, denominator] = value.split('/');

        return Number(numerator) / Number(denominator);
    }

    return Number(value);
}

get doorHeightTotalFeet() {
    const entered =
        Number(this.state.doorHeightFeet || 0) +
        Number(this.state.doorHeightInches || 0) / 12;

    // The drum's nameplate height is a CAP, not just something to warn about.
    // The reference freezes its answer at maxHeight: on D400-96 at 375 lb the
    // multiplier, turns and TIPPT are identical at 96", 108", 120", 132" and
    // 144" - 0.281015 / 8.1 / 105.4 throughout - so the length stops at 20.25
    // instead of climbing. We were feeding the entered height straight in and
    // growing the spring to 29.25.
    //
    // Same shape as the hi-lift weight clamp: the limit was already sitting in
    // DRUM_LIMITS and the Duplex path simply never consulted it. maxHeight was
    // only ever used for the Single warning below.
    //
    // NOW APPLIED TO SINGLE TOO. It was Duplex-only, on the standing
    // instruction not to move the Single path. That instruction was given
    // because Single was correct, and for every door at or under the drum's
    // nameplate it still is - the readings match exactly. Past the nameplate
    // it was not: the reference freezes, we kept climbing, and on a D400-96
    // at 144" the multiplier was 0.182830 against the reference's 0.257806,
    // 29% out. Twelve Single readings show the freeze directly, six on each
    // of two drums.
    //
    // Standard lift only. The hi-lift drums are absent from DRUM_LIMITS,
    // which is also correct: D800-120 tracks the entered height past its
    // nameplate 120 all the way to 192".
    // Hi-lift drums keep their caps in HILIFT_DRUMS, and they DO have height
    // caps - 384, 264 and 234 inches - which this used to skip entirely on the
    // grounds that the hi-lift drums were absent from DRUM_LIMITS. They were
    // absent from the wrong table, not uncapped.
    const limits = (this.state.liftType === "Hi-Lift"
        ? HILIFT_DRUMS[this.state.drum]
        : null) || DRUM_LIMITS[this.state.drum];

    if (!limits || !limits.maxHeight) {
        return entered;
    }

    return Math.min(entered, limits.maxHeight / 12);
}

// The height as TYPED, unclamped. The warning below has to compare against
// this: doorHeightTotalFeet is now the effective height, so asking it whether
// the door is too tall can only ever answer no.
get doorHeightEnteredFeet() {
    return (
        Number(this.state.doorHeightFeet || 0) +
        Number(this.state.doorHeightInches || 0) / 12
    );
}

get doorWidthTotalInches() {
    return (
        Number(this.state.doorWidthFeet || 0) * 12 +
        Number(this.state.doorWidthInches || 0)
    );
}

get drumData() {
    return DRUMS[this.state.drum] || null;
}

get hiLiftDrumData() {
    return HILIFT_DRUMS[this.state.drum] || null;
}

get hiLiftInches() {
    return Number(this.state.liftin) || 0;
}

get rEffExact() {
    // Effective drum radius at full wind. Constant for a standard drum;
    // set by the hi-lift alone (never by door height) for a hi-lift drum.
    if (this.hiLiftDrumData) {
        const drum = this.hiLiftDrumData;
        const raw = drum.catalog
            ? drum.reff(this.hiLiftInches)
            : hiLiftREff(drum, this.hiLiftInches);

        return HILIFT_RADIUS_SCALE * raw;
    }

    return this.drumData ? this.drumData.rEff : 0;
}

get turnsExact() {
    // Full-precision turns at the current door height. Everything computes
    // from this; `turns` below is only what the Turns row shows.
    //
    // The two drum families are solved in opposite directions. A standard
    // drum has a smooth turns curve and the multiplier falls out of it; a
    // hi-lift drum has a smooth MULTIPLIER and the turns fall out of that,
    // which is what lets turns go to a pole where the multiplier crosses zero.
    if (this.hiLiftDrumData) {
        const multiplier = this.multiplierExact;

        // Not `> 0`: past the drum's range the multiplier genuinely goes
        // negative and the reference shows the negative turns that follow,
        // so only an exact zero is guarded here.
        return multiplier !== 0 ? this.rEffExact / multiplier : 0;
    }

    if (!this.drumData) {
        return 0;
    }

    return (
        drumTurns(this.drumData, this.doorHeightTotalFeet) -
        radiusTurnDrop(
            this.state.drum,
            this.state.radius,
            this.doorHeightTotalFeet
        )
    );
}

// ONE DECIMAL, because that is what the reference prints and what the user
// is comparing against. Across 4,712 readings it gives turns to a tenth -
// 11.2, never 11.18 - and TIPPT the same. Showing two decimals made our
// figures disagree with the website almost everywhere even when the
// arithmetic underneath was identical: turns matched in 245 of 4,210 Duplex
// readings at two decimals and 4,085 at one.
//
// DISPLAY ONLY, both of these. Nothing computes from them - cycles come from
// turnsExact and tipptExact and reproduce the reference's own figure on all
// 288 Single readings we hold, so rounding the inputs to a tenth before
// computing would be a different change and a worse one: measured, it drops
// that agreement from 288/288 to 145/288.
get turns() {
    return Math.round(this.turnsExact * 10) / 10;
}

// The Wire Size dropdown. Hidden on Duplex, where the outer and inner
// springs each carry their own wire size in the results and one shared
// selection above them would be meaningless.
//
// The auto-pick still runs underneath and still writes state.wireSize; it
// is simply not on screen. Nothing reads it in Duplex, whose results are
// placeholder zeros, so leaving it alone keeps Single unchanged when the
// assembly is switched back.
get wireSizeVisible() {
    return this.resultsVisible && this.state.assembly !== "Duplex";
}

get multiplierExact() {
    if (this.hiLiftDrumData) {
        const drum = this.hiLiftDrumData;

        if (drum.catalog) {
            return drum.multiplier(this.doorHeightTotalFeet, this.hiLiftInches);
        }

        return hiLiftMultiplier(
            drum,
            this.doorHeightTotalFeet,
            this.hiLiftInches
        );
    }

    // Derived from turns via the constant drum radius, which is what keeps the
    // cycle count height-independent.
    if (!this.drumData || !this.turnsExact) {
        return 0;
    }

    return this.rEffExact / this.turnsExact;
}

get resultsVisible() {
    // Nothing is shown until the calculator has what it needs: a drum, and a
    // weight above zero. Without both, every result would read 0 or NaN,
    // which looks like an answer rather than a missing input.
    if (!this.state.drum) {
        return false;
    }

    if (!(Number(this.state.weight) > 0)) {
        return false;
    }

    // Hi-lift needs one more: the hi-lift itself. This keys off the LIFT TYPE
    // rather than whether the drum has a model behind it, so an unimplemented
    // hi-lift drum is gated the same way.
    //
    // Note this is the one input the reference calculator also refuses -
    // it hides its results rows at a hi-lift of zero. Everything else it
    // computes and shows, including past a drum's published range where the
    // multiplier crosses zero and goes NEGATIVE: on the D800-120 a 7'0" door
    // returns -0.000230 at 96" of hi-lift, -0.173892 at 108" and -0.362278 at
    // 120". Those are not engineering answers, but they are what the
    // reference produces, and matching it is the point.
    if (this.state.liftType === "Hi-Lift" && !(this.hiLiftInches > 0)) {
        return false;
    }

    return true;
}

get multiplier() {
    // The reference calculator shows 6 decimals.
    return Math.round(this.multiplierExact * 1000000) / 1000000;
}

get tipptExact() {
    // Unrounded IPPT. NOTHING computes from the rounded `tippt` below - it is
    // display only. An earlier note here claimed the reference rounded IPPT
    // before the spring-length formula; that is wrong, and it was checked
    // directly. On D400-96, 10'0", 250 lb, ID 2 5/8", wire 0.25", rounding
    // gives 38.58" where the reference says 38.57". The hi-lift drum gives
    // three more counterexamples (10'0"/12" and 9'0"/36" on 525-54HL), with
    // none the other way.
    //
    // Cycle life likewise must use the unrounded value: it varies as the
    // 4.67th power of torque, so a 0.01 rounding of IPPT moves the cycle
    // count by ~0.05% - enough to miss by 179 cycles at 150 lb.
    return this.multiplierExact * Number(this.state.weight || 0);
}

get tippt() {
    // Display only, to one decimal - see `turns` above.
    return Math.round(this.tipptExact * 10) / 10;
}

get wireSizeNumber() {
    return Number(this.state.wireSize.replace('"', '').trim());
}

get meanDiameter() {
    // Mean coil diameter. OD = ID + 2*wire, so the mean of ID and OD is
    // ID + wire. The previous "ID + wire/2" understated it, which stretched
    // every computed length by a factor that grew as the ID shrank.
    return this.springIdNumber + this.wireSizeNumber;
}

get divider() {
    return (
        (30000000 * Math.pow(this.wireSizeNumber, 5)) /
        (TORSION_CONSTANT * this.meanDiameter)
    );
}

get springTorque() {
    // Torque carried by ONE spring at full wind, in in-lb. Set entirely by the
    // door and drum - spring geometry does not enter it.
    if (!this.state.springs || !this.turnsExact) {
        return 0;
    }

    return (this.tipptExact / this.state.springs) * this.turnsExact;
}

cyclesForWire(wire) {
    const torque = this.springTorque;

    if (!torque || !wire) {
        return 0;
    }

    // The hi-lift radius scale is carried into the coefficient too, so that
    // the ratio the cycle count actually depends on is unchanged.
    const coefficient = this.hiLiftDrumData
        ? CYCLE_COEFFICIENT * HILIFT_RADIUS_SCALE
        : CYCLE_COEFFICIENT;

    return Math.pow(
        (coefficient * Math.pow(wire, CYCLE_WIRE_EXPONENT)) / torque,
        CYCLE_EXPONENT
    );
}

get cycleLife() {
    const cycles = this.cyclesForWire(this.wireSizeNumber);

    return cycles ? Math.round(cycles).toLocaleString("en-US") : 0;
}

get cycleTarget() {
    return Number(String(this.state.cycles).replace(/,/g, "")) || 0;
}

// The wire the calculator picks on its own: the SMALLEST size whose cycle
// life reaches the Cycles target.
//
// Established from 14 reference runs and matching all 14. The only input
// that matters is the torque one spring carries, weight * rEff / springs,
// which is why weight and spring count dominate and the drum and hi-lift
// move it too - they reach torque through rEff. Door height, radius and
// spring ID were each measured and change nothing: rEff does not depend on
// height, radius moves turns and the multiplier in opposite directions so
// their product is unchanged, and spring ID never enters torque at all.
//
// 600 lb on 2 springs and 300 lb on 1 both give 682.61 in-lb and both pick
// 0.3195", which is what rules out any rule based on weight or spring count
// separately.
//
// If no size reaches the target the largest is returned, which is what the
// reference does: 250,000 and 300,000 both land on 0.3195" because that wire
// is good for 318,763 cycles and nothing larger is needed for either.
get recommendedWire() {
    // Tied to resultsVisible so the wire is only ever changed while there is
    // something on screen. Otherwise picking a hi-lift drum before entering
    // a hi-lift would silently rewrite the wire behind a hidden row.
    if (!this.resultsVisible || !this.springTorque || !this.cycleTarget) {
        return null;
    }

    for (const wire of WIRE_SIZES) {
        if (this.cyclesForWire(wire) >= this.cycleTarget) {
            return wire;
        }
    }

    return WIRE_SIZES[WIRE_SIZES.length - 1];
}

get springLengthExact() {
    if (!this.tipptExact) {
        return 0;
    }

    const endCoils =
        this.springIdNumber > LARGE_ID_THRESHOLD
            ? END_COILS_LARGE_ID
            : END_COILS_SMALL_ID;

    const endAddition = endCoils * this.wireSizeNumber;

    // Unrounded IPPT, not the 2-decimal display value. The hi-lift data
    // settles this: at 10'0"/12" the rounded IPPT gives 25.51" where the
    // reference says 25.52", and at 9'0"/36" it gives 25.12" against 25.11" -
    // two clean counterexamples, with none the other way. Rounding also
    // wrecks the collapse corner, where IPPT falls under 1 in-lb and a 0.005
    // rounding moves the spring length by ten inches (4'0"/54": 3869.59" from
    // the rounded value against a reference 3858.95").
    return (this.state.springs * this.divider) / this.tipptExact + endAddition;
}

// QUARTER INCH, because that is what the reference quotes and what can be
// bought. Springs are made to a quarter and the reference's own answers are
// always a multiple of 0.25 - 30, 33.25, 51.5, 60, 85.75 - while this returned
// two decimals of the raw computation: 33.20 where the reference says 33.25,
// 51.45 where it says 51.5.
//
// Measured against 176 external readings, feeding the reference's own wire
// choice back in so the comparison is like for like:
//
//   as it was returned, two decimals      4/176    2.3%
//   rounded to the nearest 1/4"         123/176   69.9%
//   rounded to the nearest 1/8"          60/176   34.1%
//
// The remaining 30% is not this rule: the length is right exactly where the
// multiplier is (69.9% against 70.5%), so what is left is multiplier error.
//
// WHY THIS SURVIVED. dev/single-check.mjs only ever checked the MULTIPLIER,
// and only on hand-picked readings, where it scored 12/12. The 725-case golden
// snapshot proves nothing moved, never that it was right. Single's length had
// never once been compared to the reference.
get springLength() {
    return Math.round(this.springLengthExact * 4) / 4;
}

get springWeight() {
    // Steel weight of one spring, in lb. See STEEL_DENSITY above.
    // `meanDiameter` is springID + wire, which is exactly the coil diameter
    // the wire follows.
    if (!this.springLengthExact || !this.wireSizeNumber) {
        return 0;
    }

    // FROM THE QUARTER-INCH LENGTH, not the raw one, because that is the
    // spring that gets built. Proved by inverting the reference's own reported
    // weights: across 7,941 of them the length implied by the weight matches
    // the length the reference REPORTS to within 0.005" in 99.9% of cases, so
    // it weighs the spring it quotes rather than the unrounded computation.
    const volume =
        ((Math.PI ** 2) / 4) *
        this.wireSizeNumber *
        this.meanDiameter *
        this.springLength;

    return Math.round(STEEL_DENSITY * volume * 100) / 100;
}

// --- Duplex results ------------------------------------------------------
// All of this is gated on isDuplex, so the Single path is untouched.

get isDuplex() {
    return this.state.assembly === "Duplex";
}

get duplexSpringCount() {
    return Number(this.state.springs) || 2;
}

// THE DOOR WEIGHT THE DRUM WILL ACTUALLY CARRY.
//
// The reference CAPS the weight at the drum's rating and recomputes, saying so
// as it goes: "The current weight entered is heavier than this drum will
// allow! The weight will be set to the drums maximum weight of 530". It is not
// just a warning - the whole answer that comes back is for the capped weight.
// A 620 lb door on the D400-96 returns TIPPT 151.9, which is 0.286584 x 530,
// not x 620.
//
// Two readings confirm it: 620 lb on the D400-96 computed at 530, and 765 lb on
// the D400-144 computed at 750.
//
// This app used to warn and then compute on the entered figure, which gave a
// different wire AND a 1.25" different spring on that 620 lb door - a different
// part ordered. The warning (see `warnings`) is unchanged and still fires;
// what changes is that the arithmetic now honours it.
//
// CONFINED TO DUPLEX, which is why this exists instead of clamping inside
// tipptExact. The cap is a property of the DRUM, so the Single path almost
// certainly needs it too - but Single has no reference reading to confirm the
// behaviour and is explicitly out of scope, so it is left alone and this is
// recorded as a known inconsistency rather than a silent change. One Single
// reading over a drum's rating would settle it.
get duplexEffectiveWeight() {
    const entered = Number(this.state.weight) || 0;
    // Hi-lift drums carry their rating in HILIFT_DRUMS, not DRUM_LIMITS, and
    // looking only in the latter meant hi-lift was never clamped at all. The
    // reference clamps 575-120 and 525-54HL at 1000 lb - entering 1005 already
    // comes back as 1000 - so above that we were computing TIPPT on a weight
    // the reference had thrown away, and picking a stiffer pair than it did.
    // Measured by backing the weight out of the reference's own TIPPT and
    // multiplier: see the 575/525 w1200 readings.
    const limits = (this.state.liftType === "Hi-Lift"
        ? HILIFT_DRUMS[this.state.drum]
        : null) || DRUM_LIMITS[this.state.drum];

    if (!limits || !limits.maxWeight) {
        return entered;
    }

    return Math.min(entered, limits.maxWeight);
}

// TIPPT on the effective weight. Everything in the Duplex path computes from
// this rather than tipptExact, which stays on the entered weight for Single.
get duplexTipptExact() {
    return this.multiplierExact * this.duplexEffectiveWeight;
}

// Scales K, which sets the TORQUE one spring carries and hence the cycle
// count. Every K in the table was fitted at 2 springs, so this is the factor
// off that baseline. Exactly reciprocal in the spring count.
get duplexTorqueScale() {
    return Math.pow(this.duplexSpringCount / 2, DUPLEX_TORQUE_COUNT_EXPONENT);
}

get duplexPair() {
    const key = DUPLEX_ALIASES[this.state.springId] || this.state.springId;

    return DUPLEX_PAIRS[key] || null;
}

// Cycle life for one wire combination. K is the spring's body length times
// TIPPT, so the body is K/TIPPT and the rate follows; the rest is the
// standard cycle formula on the inner spring, which is the one the reference
// reports.
//
// K IS NOT THE ACTIVE LENGTH, which is the surprise here. The LENGTH turned
// out to need no fitted constant at all - it is springs x (d_out + d_in) /
// TIPPT, the catalog formula - so the obvious next step was to use that same
// active length as the cycle body, which is exactly equivalent to setting
// K = S. It was tried and it is WORSE: the wire choice falls from 9 of 11
// reference readings to 6 of 11. The fitted K is kept because it selects
// better, not because it is understood.
//
// WHAT IS STILL WRONG HERE. Inverting the reference's own reported cycle
// counts needs 3-5% more torque on the inner spring than the physical active
// length produces, and the implied correction is not constant - it runs 1.003
// to 1.117 across eleven readings, mean 1.0390. Neither the inner spring
// alone nor the outer alone reproduces the counts. So the duplex cycle model
// is the one piece still fitted rather than derived, and the two remaining
// wire misses (both 1-spring, both one step too stiff) are its doing.
//
// THE WAHL LEAD, worth picking up when there are more readings.
//
// The standard torsion-spring curvature correction - the Wahl inner-fibre
// factor Ki = (4C^2 - C - 1)/(4C(C - 1)), C = mean diameter / wire - averages
// 1.0500 over these same eleven readings, against the 1.0390 they need. The
// same size, which is suggestive: it would mean the reference corrects the
// inner-fibre stress and this model does not.
//
// Implemented and measured, as body = active length x Ki, which drops K
// ENTIRELY and makes the whole duplex model derived:
//
//     fitted K (what is here)      wire  9/11     length 7/11
//     physical active length only  wire  6/11     length 4/11
//     active length x Ki           wire  9/11     length 7/11
//
// A TIE, so it is not in yet - but it is a tie against 17 fitted constants
// plus four slope/intercept terms, and K is demonstrably unsound where there
// are no readings: on the 2 5/8" inside 5 1/4" pair, which has NO reference
// readings at all, K/S spans 0.616 to 1.122 and trends monotonically with
// wire size. That is a systematic error, not scatter. Ki spans 1.044 to 1.065
// across both pairs.
//
// WHAT STOPPED IT. Ki runs ~8% low on the 470 lb 1-spring reading, which puts
// 0.3195/0.2625 just under a 10,000 target and selects the softer
// 0.3195/0.25 instead - a pairing the reference never uses. It also exposed a
// REAL latent bug worth recording: cycle life is NOT monotonic along the
// ladder, because a softer pair has a longer body (less torque) but a thinner
// inner wire (less capacity), and those need not cancel. So "the first pair
// over the target" is not "the softest pair over the target". With the fitted
// K no reading or invariant currently separates them, but the ladder ordering
// cannot be relied on once the cycle model moves.
//
// The correlation between the needed correction and Ki is only r = 0.435, so
// Ki explains the SIZE of the gap and not its variation.
//
// THE TARGET SWEEP SETTLED WHAT THE CORRECTION IS NOT. With the reference's
// own lengths used as the body, so the length model is out of the picture, the
// needed correction over 14 readings is 1.0435 mean, sd 0.0295 - near enough
// CONSTANT, not the systematically varying thing Ki would give. Scanning a
// single constant correction (which is just a duplex-specific cycle
// coefficient, since cycles = (COEFF x wire^2.79 / torque)^4.67 absorbs it):
//
//     no correction                       wire  4/14
//     best constant, c in 1.0375-1.0575   wire  8/14
//     Wahl Ki                             wire  8/14
//     fitted K per combination (here)     wire  9/14
//
// A correction is unambiguously needed - 4/14 without one - and it is about
// 4%. But the fitted K still edges out both derived forms, so it stays. The
// honest reading is that one constant captures most of what K is doing and
// the remainder is not yet explained.
//
// The readings that report EXACTLY the target are the least informative here:
// four of them do, and it is not known whether that is a computed life that
// happens to land on the target or the target echoed back. The ones reporting
// a value above target are what the figures above lean on.
//
// WHAT K ACTUALLY IS - settled by a 19-reading analysis using the PHYSICAL
// active length as the body, so K is out of the picture and the residual is
// visible. The correction needed is not global and not Ki. It is PER WIRE
// PAIRING, and within one pairing it is remarkably tight:
//
//     0.2625/0.2253   11 readings   mean 1.0074   sd 0.0025
//     0.273/0.2253      1 reading        1.0261
//     0.283/0.2253      1 reading        1.0512
//     0.3065/0.2437     1 reading        1.0480
//
// Eleven readings on one pairing agreeing to a quarter of a percent is not
// noise - it is a real per-pairing quantity. And K is exactly its reciprocal:
// K/S for 0.2625/0.2253 is 0.9963, i.e. 1/1.0037, against a measured 1.0074;
// for 0.283/0.2253 it is 0.9574, i.e. 1/1.0445, against a measured 1.0512.
//
// So K is sound in principle and only badly SAMPLED. That is why the derived
// forms tie but never beat it, and it is the practical path forward: each
// pairing's K can be pinned to a fraction of a percent by two or three
// readings on that pairing, where the current values came from bracket
// midpoints.
//
// It also explains the earlier spring-count confusion. Grouping the same
// residuals by count gives 1 spring 1.0492 and 2 springs 1.0151, which looks
// like a count effect - but the 2-spring set is dominated by eleven readings
// on the softest pairing, whose correction is genuinely near 1. The split is
// by pairing, not by count.
//
// TWO FLAVOURS, AND THE DIFFERENCE MATTERS.
//
// `rounded` (the default) reproduces the reference rounding TIPPT and turns
// to ONE DECIMAL before computing: its API returns them at exactly that
// precision and computes from them, and it shows in its own output - six
// responses at a fixed load and rising height gave counts wandering 173,000
// to 182,000 for a quantity that is physically constant. Matching it nearly
// doubled the exact matches across 42 readings and halved the worst error,
// 4.77% to 2.90%. Rounding to two decimals gives the unrounded figures back
// exactly, so one decimal is the real rule and not a fudge that happens to
// help. This is what the Cycle Life row DISPLAYS.
//
// UNROUNDED IS WHAT CHOOSES THE WIRE. Peak torque at full wind is weight
// times drum radius, so turnsExact * tipptExact is identically rEff * weight
// and the cycle count does not depend on door height or track radius at all.
// The 1-decimal rounding breaks that identity and injects a ~5% wobble. Since
// the wire is picked by comparing the count against the target, that wobble
// was flipping a DISCRETE choice worth inches of spring: a 688 lb door went
// 0.289 -> 0.283 -> 0.289 as it got TALLER. Measured on the D400-144, 85
// weights changed wire with height alone and 105 weight/spring-count
// combinations changed wire with track radius alone.
//
// So the decision is made on exact values and only the printout is rounded.
// dev/replay.mjs enforces both independences.
duplexCyclesForStep(step, { rounded = true } = {}) {
    const pair = this.duplexPair;

    if (!step || !pair || !this.duplexTipptExact || !this.turnsExact) {
        return 0;
    }

    // TIPPT and turns are rounded to ONE DECIMAL first, because the reference
    // does: its API returns them at exactly that precision and computes from
    // them. It shows in its own output - six responses at a fixed load and
    // rising height gave cycle counts wandering 173,000 to 182,000 for a
    // quantity that is physically constant, which is the rounding, not the
    // spring.
    //
    // Replicating it nearly doubled the exact matches across 42 readings and
    // halved the worst error, 4.77% to 2.90%. Rounding to two decimals gives
    // back the unrounded figures exactly, so one decimal is the real rule and
    // not a fudge that happens to help.
    //
    // CONFINED TO DUPLEX. tipptExact and turnsExact are untouched, so nothing
    // in the Single path moves.
    // ROUNDED FOR DISPLAY ONLY - never for the wire decision. See the note
    // below the formula.
    const tippt = rounded
        ? Math.round(this.duplexTipptExact * 10) / 10
        : this.duplexTipptExact;
    const turns = rounded
        ? Math.round(this.turnsExact * 10) / 10
        : this.turnsExact;

    const body = (step.K * this.duplexTorqueScale) / tippt;
    const divider =
        (30000000 * Math.pow(step.innerWire, 5)) /
        (TORSION_CONSTANT * (pair.innerId + step.innerWire));
    const torque = (divider / body) * turns;

    if (!torque) {
        return 0;
    }

    return Math.pow(
        (CYCLE_COEFFICIENT * Math.pow(step.innerWire, CYCLE_WIRE_EXPONENT)) /
            torque,
        CYCLE_EXPONENT
    );
}

// Every wire combination the calculator may choose from, smallest first.
//
// The measured ones lead, in the order the reference was seen to use them.
// After those the list CONTINUES, generated across the whole WIRE_SIZES
// table, so a heavy or tall door can never run off the end - which is what
// went wrong before: the table stopped at 0.2730/0.2253 and every door past
// it silently got that combination and badly wrong numbers.
//
// Generated entries get C and K from a LINE through S = 2*(outer divider +
// inner divider), the quantity the two springs' rates sum to.
//
// A fixed RATIO to S was tried first and was not good enough: C/S drifts from
// 1.027 to 0.997 and K/S from 0.995 to 0.949 as the springs stiffen, and a
// 749 lb door at 10'8" landed on an estimated C 2% high - which pushed x past
// a rounding boundary and added a whole 1.25" to the length. On a rule that
// rounds to the inch, a 2% error in C is not a 2% error in the answer.
//
// A line holds the measured points to about 1%. They are still ESTIMATES, and
// duplexExtrapolated flags when one is in use.
get duplexCandidates() {
    const pair = this.duplexPair;

    if (!pair) {
        return [];
    }

    const divider = (wire, id) =>
        (30000000 * Math.pow(wire, 5)) / (TORSION_CONSTANT * (id + wire));

    const stiffness = (c) =>
        2 *
        (divider(c.outerWire, pair.outerId) +
            divider(c.innerWire, pair.innerId));

    const out = pair.calibration.map((c) => ({
        ...c,
        S: stiffness(c),
        measured: true,
    }));
    const seen = new Set(out.map((c) => c.outerWire + "/" + c.innerWire));

    // THE LIST IS CAPPED PER CYCLE TARGET.
    //
    // Torsion springs are sold BY CYCLE RATING - a 10,000-cycle line, a
    // 25,000-cycle line - so the target picks which catalogue is on offer,
    // not merely a threshold to clear. Two 750 lb doors at 8'0" and 12'0",
    // both at a 10,000 target, both stop dead at 0.2950/0.2343 and say so:
    // "cycle life calculation of 9,000.00 is less than the 10,000 cycle
    // minimum". The same door at 25,000 uses 0.3195/0.2625 without trouble.
    // The combination exists; it was not AVAILABLE at the lower target.
    //
    // (Those two doors landing on the same 9,000 is itself a good check: peak
    // torque is weight times drum radius and does not depend on height, so
    // one door weight gives one cycle life at every height. 196.4 x 8.8 and
    // 139.2 x 12.4 are both 1727.)
    //
    // An earlier note blamed door width for the same behaviour. That was
    // wrong - changing the width changes nothing in the reference's output.
    // THE LADDER IS THE WHOLE CROSS PRODUCT, not a tail hung off the last
    // measured entry.
    //
    // It used to start generating at the indices of the LAST calibration row
    // (0.375/0.3065), so every combination softer than that and not explicitly
    // measured was unreachable. Three reference readings land on exactly such
    // combinations - 0.331/0.2625, 0.3437/0.273 and 0.3625/0.295, none of them
    // in the table - and the app answered each with the next rung it did have,
    // one step too stiff.
    //
    // Generating the full product is only safe now that the LENGTH needs no
    // fitted constant: a generated rung's length is exact, because it comes
    // from its own two wire sizes. Before duplexActiveLength it would have
    // carried a C estimated to about 1%, and a 1% error in C moved 22.7% of
    // lengths by a whole inch - which is why this was left alone until the
    // length rule was settled.
    //
    // What a generated rung still estimates is K, and therefore its cycle
    // count. duplexExtrapolated reports when one is in use.
    const extra = [];

    // GENERATION ONLY ABOVE THE CATALOGUE, never between its rungs.
    //
    // This is the change that made the ladder work. Generating rungs that
    // interleave with the catalogue is what produced the phantoms: 0.289/0.2253
    // has a stress balance of 1.0400 and is never used by the reference, while
    // 0.3625/0.283 has a balance of 1.0400 and IS used, so no rule in this file
    // can tell them apart. Inside the catalogue's range the catalogue is the
    // authority; past its stiffest rung a heavy door still needs somewhere to
    // go, and only there is a rung invented.
    //
    // A generated rung's K is estimated from the balance law just below.
    // duplexExtrapolated still reports when one is in use.
    //
    // This replaced, in turn, a kSlope line that ran 8.5% low on the first
    // rung past the table, and then the catalogue's median K/S - which was
    // better than the line and is still 17% to 34% out at the stiff end,
    // because K/S is not constant.
    //
    // K/S IS NOT CONSTANT ALONG THE LADDER - it tracks the stress balance.
    //
    // Across the 44 calibrated rungs K/S runs 0.72 to 0.99, and it falls as
    // the outer spring becomes relatively more stressed: Pearson r = -0.906
    // against the balance ratio. A single median ratio therefore misses by up
    // to 25%, and it misses worst exactly where it is used - at the stiff end,
    // past the catalogue, where the balance is furthest from the middle.
    //
    // Fitting K/S = a + b*balance on the 40 well-pinned rungs and testing it
    // on the two whose K has no switch point behind it, so they were never in
    // the fit:
    //
    //                    balance law   median ratio
    //   0.5625/0.4305       6.4% off     17.3% off
    //   0.625/0.4615       14.3% off     34.2% off
    //
    // Two to three times better where it matters. The law is NOT good enough
    // to replace a measured K - its worst error on the rungs it was fitted to
    // is 6.5%, against the 0.15% a switch point gives - so it is used only for
    // GENERATED rungs, which had no measurement in the first place.
    const fits = pair.calibration.map((c) => {
        const stiffness =
            2 *
            (divider(c.outerWire, pair.outerId) +
                divider(c.innerWire, pair.innerId));

        return {
            ratio: c.K / stiffness,
            balance:
                duplexSpringStress(c.outerWire, pair.outerId) /
                duplexSpringStress(c.innerWire, pair.innerId),
        };
    });
    const mean = (xs) => xs.reduce((t, v) => t + v, 0) / xs.length;
    const mBal = mean(fits.map((f) => f.balance));
    const mRatio = mean(fits.map((f) => f.ratio));
    const varBal = mean(fits.map((f) => (f.balance - mBal) ** 2));
    const slope = varBal
        ? mean(fits.map((f) => (f.balance - mBal) * (f.ratio - mRatio))) / varBal
        : 0;
    const intercept = mRatio - slope * mBal;
    const ratioFor = (outerWire, innerWire) =>
        intercept +
        slope *
            (duplexSpringStress(outerWire, pair.outerId) /
                duplexSpringStress(innerWire, pair.innerId));
    const stiffest = Math.max(...out.map((c) => c.S));

    for (let o = 0; o < WIRE_SIZES.length; o++) {
        for (let i = 0; i < WIRE_SIZES.length; i++) {
            const outerWire = WIRE_SIZES[o];
            const innerWire = WIRE_SIZES[i];
            const key = outerWire + "/" + innerWire;

            if (seen.has(key)) {
                continue;
            }

            if (!duplexPairBalanced(pair, outerWire, innerWire)) {
                continue;
            }

            const S =
                2 *
                (divider(outerWire, pair.outerId) +
                    divider(innerWire, pair.innerId));

            if (S <= stiffest) {
                continue;
            }

            seen.add(key);

            extra.push({
                outerWire,
                innerWire,
                K: S * ratioFor(outerWire, innerWire),
                S,
                measured: false,
            });
        }
    }

    // Sorted MEASURED AND GENERATED TOGETHER. Listing the measured ones first
    // was a bug: 0.2830/0.2343 is in the table and 0.2830/0.2253 was not, so a
    // 500 lb door on the D525-216 took the stiffer pair and came out an inch
    // long where the reference had used the weaker inner. The two wires do not
    // step in lockstep, so "the next combination up" has to be decided by
    // total stiffness, not by which ones happen to have been measured.
    //
    // The catalogue limit applies to MEASURED entries too. A combination being
    // in the table means it was seen once, not that it is on offer at every
    // cycle target: 0.3195/0.2625 is measured, and at a 10,000 target the
    // reference will not use it.
    const all = out
        .concat(extra)
        .filter((c) =>
            duplexPairBuildable(pair, c.outerWire, c.innerWire, c.measured)
        )
        .sort((a, b) => a.S - b.S);

    // Never return nothing - if the cycle-rating limit excludes everything,
    // fall back to the softest BUILDABLE combination rather than leaving the
    // caller empty. The buildability gate is not negotiable here: a pair that
    // cannot be wound is worse than no suggestion.
    if (all.length) {
        return all;
    }

    const buildable = out
        .filter((c) =>
            duplexPairBuildable(pair, c.outerWire, c.innerWire, c.measured)
        )
        .sort((a, b) => a.S - b.S);

    return buildable.length ? [buildable[0]] : [];
}

// The wire combination the reference picks: the SMALLEST whose cycle life
// reaches the target. Same rule the Single path uses.
//
// KNOWN GAP - THIS IS NOT THE WHOLE RULE. Raising the cycle target on one
// 750 lb 12'0" door walks the reference up its sequence:
//
//   target  10,000 -> 0.2950/0.2343    9,000 cycles   BELOW target
//   target  25,000 -> 0.3195/0.2625   31,000 cycles   above
//   target  50,000 -> 0.3310/0.2730   49,000 cycles   BELOW target
//   target 100,000 -> 0.3625/0.2830  115,000 cycles   above
//
// Twice it takes a combination that does not reach the target, so "smallest
// meeting the target" is not what it does.
//
// CONFIRMED BY A REJECTION BOUNDARY. At 725 lb the reference returns 9,000
// cycles with status 'warning' - "cycle life calculation of 9,000.00 is less
// than the 10,000 cycle minimum" - and KEEPS 0.289/0.2343 rather than
// stepping up. At 730 lb it does step up, to 0.295/0.2343. So it genuinely
// tolerates undershooting the target, and the 725/730 pair brackets where the
// step happens.
//
// "Closest to target" was then tested directly as the alternative, scored in
// log space so an equal factor over and under weighs the same: 10 of 24
// readings against the shipped rule's 18. So it is not that either.
//
// WHAT IT ACTUALLY IS: ~90% OF TARGET. Two rejection boundaries pin it. At
// 685 lb the reference keeps 0.283/0.2343 at 9,000 cycles with a warning and
// steps to 0.289 at 690; at 725 lb it keeps 0.289/0.2343 at 9,000 and steps
// to 0.295 at 730. Both boundaries sit at 9,000 against a 10,000 target -
// exactly 0.90.
//
// Confirmed a third way without using any K from this file: 620 lb measures
// 14,000 cycles on 0.283/0.2253, and 14,000 / (680/620)^4.67 = 9,000, so at
// 680 lb that rung falls to the boundary - which is exactly where the
// reference steps off it.
//
// AND IT IS STILL NOT IMPLEMENTED, because it makes the result worse here:
//
//     f = 1.00   15/27       f = 0.92   12/27
//     f = 0.98   15/27       f = 0.90   11/27
//     f = 0.95   14/27       f = 0.85    9/27
//
// A looser threshold lets more rungs qualify and so amplifies every error in
// K. At 680 lb this model still thinks 0.283/0.2253 clears the target where
// the reference's own numbers put it at 9,000. The strict f = 1.00 in use is
// compensating for optimistic K.
//
// THAT IS THE THIRD COMPENSATING ERROR FOUND - with DUPLEX_CATALOGUE's cap and
// the pessimistic kSlope line. Each measures worse when corrected alone, which
// is the signature of a stack of errors fitted against each other. K is the
// one underneath: fix it per rung and the cap, the threshold and the ladder can
// all then be corrected together.
//
// THE LADDER IS PARTLY A CATALOGUE, not purely a rule. 0.289/0.2253 has a
// stress balance of 1.0400 and is NEVER used by the reference, while
// 0.3625/0.283 has a balance of 1.0400 and IS used. Identical by every
// criterion in this file, opposite verdicts. Seventeen pairings have now been
// observed and they form a regular ladder in 7-13% stiffness steps; the
// generated list offers 45 rungs up to the same stiffness, 28 of them never
// seen.
//
// Restricting the ladder to the 17 observed rungs was measured: 16 of 23 with
// the line-fitted K, 17 of 23 with K = S, against the generated ladder's 18.
// Not an improvement YET, because the observed rungs that are not in
// DUPLEX_PAIRS have no measured K - but it is the shape of the eventual fix,
// and it needs a measured K per rung rather than a better guess.
//
// BOTH K ESTIMATES ARE COMPENSATING ERRORS, which is worth recording because
// each looks like an obvious improvement on its own. The kSlope line runs
// ~8.5% low on rungs past the table (6095 against S = 6665 for 0.3437/0.273),
// which makes a generated rung look pessimistic, skips it, and lands one step
// too stiff - every remaining wire miss has that shape. But replacing it with
// K = S scores 9 of 24, far worse, because the line's pessimism is what
// suppresses the 28 spurious generated rungs. Fixing either one alone makes
// the result worse; the ladder and K have to be fixed together. The sequence is coarse - a wire
// step is about a threefold jump in cycle life, since life goes as roughly
// the thirteenth power of wire - so the reference is taking whichever
// neighbour lands nearest, not the first one over.
//
// DOOR WIDTH IS NOT INVOLVED. An earlier note here blamed it, reasoning that
// the 10,000 case fell back because 0.3195/0.2625 is 37" long and would not
// fit a 108" opening. That was wrong: changing the door width changes nothing
// in the reference's output. Width only ever drives the too-long message.
//
// "Closest to target" was tried as the unifying rule: it reproduces the sweep
// above exactly and breaks SEVEN other readings. It may still be the right
// rule with cycle counts this model cannot compute finely enough - near a
// step the two neighbours can sit within a percent of each other, which is
// inside this model's error.
//
// The cost is one reading: that 750 lb 12'0" door at 10,000, which picks
// 0.3195/0.2625 here and comes out 14" long. Every other reading is right.
get duplexStep() {
    const pair = this.duplexPair;

    if (!pair || !this.duplexTipptExact) {
        return null;
    }

    const candidates = this.duplexCandidates;
    const target = this.cycleTarget;

    // NO TOLERANCE. There was one, growing from 0.1% to 3% as each boundary
    // case arrived, and it was the wrong tool throughout - it was hiding K
    // values that sat too low.
    //
    // What killed it: a 683 lb door computing 9,882 that the reference
    // ACCEPTS, against a 727 lb door computing 9,967 that it REJECTS. The
    // rejected case computes HIGHER than the accepted one, so no single
    // threshold can separate them. They are different wire combinations, and
    // the fault was K for 0.283/0.2343, not the comparison.
    //
    // Fixed at the cause instead. Each K is now bracketed by what its own
    // readings prove: a reading that was SELECTED had cycles at or above the
    // target, and its displayed count fixes them within 500. Those two
    // together pin K to a few units, where a cycle count alone allowed
    // dozens. The comparison can then be exact, as the reference's is.
    // THE SOFTEST RUNG REACHING THE ACCEPTANCE FRACTION OF THE TARGET.
    //
    // Searched rather than taken first in order, because cycle life is not
    // monotonic along the ladder: a softer rung has a longer body and so less
    // torque per spring, but a thinner inner wire and so less capacity, and
    // those need not cancel.
    if (target) {
        const reach = target * DUPLEX_ACCEPT_FRACTION;
        let best = null;

        for (const step of candidates) {
            if (this.duplexCyclesForStep(step, { rounded: false }) < reach) {
                continue;
            }

            if (!best || step.S < best.S) {
                best = step;
            }
        }

        if (best) {
            return best;
        }
    }

    return candidates[candidates.length - 1] || null;
}

// True when the chosen combination was never measured, so its length, weight
// and cycle figures are estimates from the pair's ratios rather than readings.
get duplexExtrapolated() {
    const step = this.duplexStep;

    return !!step && !step.measured;
}

// False once the load runs past the last measured wire combination, where
// the numbers are an extrapolation rather than a reading.
get duplexCalibrated() {
    return !!this.duplexPair && !this.duplexExtrapolated;
}

get duplexInnerLength() {
    return duplexSnapToGrid(
        duplexLength(
            this.duplexActiveLength,
            this.duplexStep,
            this.duplexSpringCount
        ),
        this.duplexSpringCount
    );
}

// Active coil length of the pair, before rounding. Exposed because the
// rounding is what is still uncertain, so the unrounded value is what a new
// reading is compared against.
get duplexActiveLength() {
    return duplexActiveLength(
        this.duplexPair,
        this.duplexStep,
        this.duplexSpringCount,
        this.duplexTipptExact
    );
}

// Always exactly an inch more than the inner - true in all 17 readings.
get duplexOuterLength() {
    const inner = this.duplexInnerLength;

    return inner ? inner + 1 : 0;
}

// Steel weight, from the ROUNDED length. The reference does the same: at a
// displayed 15.00" the outer comes back 17.25 lb to the cent, which only
// works if the weight is taken after the length is rounded.
duplexWeight(wire, springId, length) {
    if (!wire || !length) {
        return 0;
    }

    const volume =
        ((Math.PI ** 2) / 4) * wire * (springId + wire) * length;

    return Math.round(STEEL_DENSITY * volume * 100) / 100;
}

get duplexInnerWeight() {
    const step = this.duplexStep;
    const pair = this.duplexPair;

    return step
        ? this.duplexWeight(step.innerWire, pair.innerId, this.duplexInnerLength)
        : 0;
}

get duplexOuterWeight() {
    const step = this.duplexStep;
    const pair = this.duplexPair;

    return step
        ? this.duplexWeight(step.outerWire, pair.outerId, this.duplexOuterLength)
        : 0;
}

// --- Pricing ----------------------------------------------------------

// The diameters THIS configuration needs a set of cones for. Duplex nests two
// springs per shaft position and so takes a set for each diameter; Single and
// Triplex take one. Empty means the configuration cannot be priced.
//
// The Duplex diameters come from duplexPair, which has already resolved the
// aliases - a Raynor 3 1/2" inside 5 1/2" is engineered as the 2 5/8" inside
// 5 1/4" pair everywhere else in this file, so it is priced as one too.
get coneDiameters() {
    if (this.state.assembly === "Duplex") {
        const pair = this.duplexPair;

        return pair ? [pair.innerId, pair.outerId] : [];
    }

    return [this.springIdNumber];
}

// Finished steel in the whole assembly, in lb. Duplex counts both springs of
// every pair.
get assemblyWeight() {
    const springs = Number(this.state.springs) || 0;

    if (this.state.assembly === "Duplex") {
        return springs * (this.duplexInnerWeight + this.duplexOuterWeight);
    }

    return springs * this.springWeight;
}

// TRUE once the server's rates are in hand AND they cover every diameter this
// configuration needs. Without them there is no price to show: quoting the
// costs below would be quoting without the markup, which is worse than showing
// nothing.
//
// A DIAMETER WITH NO RATE IS A MISCONFIGURATION, NOT A FREE CONE. Treating a
// missing rate as zero undercharges by a whole set of cones - a 6" pair is
// about $70 at two springs - and nothing on the page would look wrong, so the
// quote is refused instead. That is not hypothetical: this read the rates by
// string key, and the server writes 6 the way Python does, as "6.0", so the 6"
// cone really was quoted free until the keys became numbers.
get priceAvailable() {
    // EVERY RATE IS TESTED FOR BEING A NUMBER, not for being truthy.
    //
    // Zero is a legitimate setting for all three of these - no labour charge, no
    // filler charge, and steel given away - and `!0` is true, so a truthiness
    // test turns a deliberate zero into "call us". That was already fixed for
    // the labour charge and then reintroduced for the steel rate when it became
    // a setting; setting it to 0 made the page refuse to quote at all.
    if (!this.rates
        || !Number.isFinite(this.rates.perLb)
        || !Number.isFinite(this.rates.labor)
        || !Number.isFinite(this.rates.fillerPerFoot)) {
        return false;
    }

    const needed = this.coneDiameters;

    return needed.length > 0 && needed.every((d) => this.rates.cones.has(Number(d)));
}

get priceCones() {
    if (!this.priceAvailable) {
        return 0;
    }

    const springs = Number(this.state.springs) || 0;
    const unit = this.coneDiameters.reduce(
        (sum, d) => sum + this.rates.cones.get(Number(d)), 0
    );

    return Math.round(springs * unit * 100) / 100;
}

get priceSteel() {
    if (!this.priceAvailable) {
        return 0;
    }

    return Math.round(this.assemblyWeight * this.rates.perLb * 100) / 100;
}

// ROUNDED PARTS, SUMMED - not the rounding of an exact total. A quote whose
// column does not add up invites someone to re-add it by hand, and both parts
// are already at the cent, so the sum is exact at the cent too.
//
// THE LABOUR CHARGE IS IN HERE AND NOWHERE ELSE ON THE PAGE. It is flat per
// assembly, so it does not scale with the spring count, and it is added after
// the marked-up materials rather than being marked up itself - the server
// decides both of those and sends the finished figure. The page shows one total
// and the cart charges the same total; there is no labour row, which is the
// whole point of it being a setting rather than a line item.
// PLASTIC FILLER, which only the 5 1/4" spring takes.
//
// One per spring, cut to that spring's own length - a 4 ft spring takes 4 ft of
// filler - so what is bought is FEET of material and the rate is per foot. The
// two prices quoted, $19.44 for 6 ft and $22.68 for 7 ft, are both exactly
// $3.24 a foot, so one rate covers them.
//
// Which ID takes one is the server's to say, not this file's: it arrives with
// the rates. That keeps the rule in the same place as the prices it applies to.
get priceFillerFeet() {
    if (!this.priceAvailable) {
        return 0;
    }

    const springs = Number(this.state.springs) || 0;
    const takesOne = (id) => Number(id) === this.rates.fillerSpringId;

    // EVERY SPRING THAT TAKES ONE, which for Duplex means checking both halves
    // of the pair rather than the assembly. The server prices the filler per
    // spring whose ID calls for it, so this has to agree exactly - when it only
    // looked at Single, dev/price-parity.sh caught the page quoting 469.34
    // against a cart charging 497.41 on a pair with a 5 1/4" outer.
    let inches = 0;

    if (this.isDuplex) {
        const pair = this.duplexPair;

        if (!pair) {
            return 0;
        }

        if (takesOne(pair.outerId)) inches += this.duplexOuterLength;
        if (takesOne(pair.innerId)) inches += this.duplexInnerLength;
    } else if (takesOne(this.springIdNumber)) {
        inches = this.springLength;
    }

    return Math.round(springs * (inches / 12) * 10000) / 10000;
}

get priceFiller() {
    if (!this.priceAvailable) {
        return 0;
    }

    return Math.round(this.priceFillerFeet * this.rates.fillerPerFoot * 100) / 100;
}

get priceTotal() {
    // Guarded like the two parts above, and not only for tidiness: this reads
    // the labour charge straight off the rates, so without the guard a page
    // whose fetch failed would throw here rather than show "call us".
    if (!this.priceAvailable) {
        return 0;
    }

    return Math.round(
        (this.priceCones + this.priceSteel + this.priceFiller + this.rates.labor) * 100
    ) / 100;
}

money(value) {
    return `$${value.toFixed(2)}`;
}

// Cycle life of the set. K is the spring's body length times TIPPT, so the
// body is K/TIPPT and the rate follows; the rest is the standard cycle
// formula on the inner spring, which is the one the reference reports.
// TRUE when no pairing on the ladder reached the cycle target and the stiffest
// available was taken instead.
//
// This is what the reference's "cycle life calculation is less than the N cycle
// minimum" actually reports. It is NOT a threshold on the cycle count, which is
// why comparing the count to a fraction of the target never worked: on all 184
// readings where the reference raises it, our wire matches EXACTLY and the pair
// we chose came from the fallback below duplexStep - we had already concluded
// nothing reached the target. The count itself cannot carry the test, because
// ours reads 9,819 where the reference reads 9,000 for the same pairing, which
// rounds the wrong side of 9,500.
get duplexSettled() {
    const target = this.cycleTarget;
    const pair = this.duplexPair;

    if (!target || !pair || !this.duplexTipptExact) {
        return false;
    }

    const reach = target * DUPLEX_ACCEPT_FRACTION;

    return !this.duplexCandidates.some(
        (step) => this.duplexCyclesForStep(step, { rounded: false }) >= reach
    );
}

get duplexCyclesExact() {
    return this.duplexCyclesForStep(this.duplexStep);
}

get duplexCycles() {
    const cycles = this.duplexCyclesExact;

    if (!cycles) {
        return 0;
    }

    const rounded =
        Math.round(cycles / DUPLEX_CYCLE_ROUNDING) * DUPLEX_CYCLE_ROUNDING;

    return rounded.toLocaleString("en-US");
}

// Display strings for the two wire sizes and the two spring IDs.
get duplexInnerWire() {
    const step = this.duplexStep;

    return step ? formatWire(step.innerWire) : "";
}

get duplexOuterWire() {
    const step = this.duplexStep;

    return step ? formatWire(step.outerWire) : "";
}

get duplexInnerId() {
    const key = DUPLEX_ALIASES[this.state.springId] || this.state.springId;

    return key ? key.split(" inside ")[0] : "";
}

get duplexOuterId() {
    const key = DUPLEX_ALIASES[this.state.springId] || this.state.springId;

    return key ? key.split(" inside ")[1] : "";
}

// How much shaft the finished assembly takes up, wound and with its hardware.
// See ASSEMBLY_HARDWARE above for where the three terms come from.
get assemblyLengthExact() {
    // DUPLEX USES ITS OWN SPRING, which it has to: springLengthExact and
    // wireSizeNumber below both come from the Single path and the Wire Size
    // dropdown, and Duplex uses neither. Reading them gave 98.86" for a 348 lb
    // 3-spring door whose assembly is really 126.33", so the too-long warning
    // never fired - and the reference calls that door unbuildable, returning
    // "Torsion assembly will be too long for a 108\" wide door!".
    //
    // That is the same leak as the stale wire warnings, except it fails the
    // dangerous way round: a spurious warning is noise, a missing one lets an
    // assembly through that will not fit the opening.
    //
    // THE OUTER SPRING GOVERNS. The pair is nested, so what the shaft sees is
    // the outer spring - it is the longer of the two by exactly an inch, and
    // its wire is the thicker, so it also grows more as it winds. Taking the
    // inner would understate the assembly twice over.
    if (this.isDuplex) {
        const outer = this.duplexOuterLength;
        const step = this.duplexStep;

        if (!outer || !step) {
            return 0;
        }

        const woundPerSpring = outer + this.turnsExact * step.outerWire;
        const hardware =
            ASSEMBLY_HARDWARE[this.duplexSpringCount] ?? ASSEMBLY_HARDWARE[2];

        return this.duplexSpringCount * woundPerSpring + hardware;
    }

    if (!this.springLengthExact) {
        return 0;
    }

    const woundPerSpring =
        this.springLengthExact + this.turnsExact * this.wireSizeNumber;

    const springs = Number(this.state.springs) || 0;

    return springs * woundPerSpring + (ASSEMBLY_HARDWARE[springs] ?? ASSEMBLY_HARDWARE[2]);
}

get assemblyLength() {
    return Math.round(this.assemblyLengthExact * 100) / 100;
}

// here ends divider

    selectSprings(event) {
        const value = parseInt(event.currentTarget.dataset.value);
        this.state.springs = value;
    }

    selectRadius(event) {
        this.state.radius = event.currentTarget.dataset.value;
    }

    togglePitch(event) {
        this.state.pitch = event.currentTarget.dataset.value === "yes";
    }

    selectAssembly() {
        // t-model already stored the new assembly. The side effect is the
        // Spring ID, which is almost certainly now a value the new dropdown
        // does not offer.
        //
        // Left alone, the browser shows its first option while the hidden
        // sizer still measures the OLD string - and since the select is
        // stretched over exactly the sizer's width, a longer value is
        // clipped. Switching to Duplex showed "3 3/4" in" because the
        // wrapper was still sized for "2 5/8"". Picking any value fixed it
        // for good, because that finally wrote the real string into state.
        //
        // Writing the new default keeps state and the DOM agreeing, which is
        // what the sizer depends on.
        const first = FIRST_SPRING_ID[this.state.assembly];

        if (first) {
            this.state.springId = first;
        }
    }

    selectLiftType() {
        // t-model already stored the new lift type. Only the side effect is
        // left: hi-lift offers no radius choice, so force it back to 15.
        if (this.state.liftType === "Hi-Lift") {
            this.state.radius = "15";
        }
    }

get drumLimits() {
    return DRUM_LIMITS[this.state.drum] || null;
}

get wireLimits() {
    return WIRE_LIMITS[this.state.springId] || null;
}

// Every warning the current inputs raise, red before yellow. Each carries its
// own severity and text so the colour and the Error Manager come from one
// place and cannot disagree.
//
// Nothing here narrows the wire the calculator picks on its own. The
// selection stays what it was - the smallest size reaching the cycle target,
// with the largest as a fallback - and is then judged. So a light door still
// lands on a wire under the ID's minimum and is told so, rather than being
// quietly bumped up to a size the reference would not have chosen.
get warnings() {
    const found = [];

    if (!this.resultsVisible) {
        return found;
    }

    // --- Wire size against the spring ID ---------------------------------
    // SKIPPED ENTIRELY ON DUPLEX. Everything from here to the end of the cycle
    // block is derived from the Wire Size dropdown, and Duplex neither uses
    // that control nor shows it (see wireSizeVisible) - it picks both wires
    // itself. Computing warnings from a stale dropdown value meant a red
    // "Low Cycle Life" fired on 7 of 8 Duplex doors, quoting a cycle count
    // with no relation to the answer on screen: at 470 lb on 2 springs it
    // claimed 1,545 cycles where the Duplex result is 21,000.
    //
    // The Duplex equivalents already exist and are reported properly - the
    // cycle count in the results row, and duplex-extrapolated below.
    //
    // THE OTHER WARNINGS STILL APPLY TO DUPLEX, deliberately. The reference
    // raises them on Duplex itself: a 348 lb 3-spring door came back with
    // "Torsion assembly will be too long for a 108\" wide door!", and a 620 lb
    // door on the D400-96 with the weight-over-max message. Suppressing those
    // would be a divergence from the reference, not a fix.
    if (!this.isDuplex) {
        const wireLimits = this.wireLimits;
        const wire = this.wireSizeNumber;

        if (wireLimits && wire) {
            if (wire > wireLimits.max) {
                found.push({
                    id: "wire-over-max",
                    severity: "red",
                    message:
                        "Wire size exceeds " +
                        wireLimits.maxText +
                        " maximum for this I.D.",
                });
            }

            if (wire < wireLimits.min) {
                found.push({
                    id: "wire-under-min",
                    severity: "red",
                    message:
                        "Wire size is less than the minimum of " +
                        wireLimits.minText +
                        " for this I.D.",
                });
            }
        }

        // --- Cycle life --------------------------------------------------
        // Exclusive by construction: a count over the ceiling cannot also be
        // under the target unless the target itself is over the ceiling, and
        // there the out-of-bounds message is the one worth showing.

        const cycles = this.cyclesForWire(wire);

        if (cycles > CYCLE_MAX) {
            found.push({
                id: "cycles-over-max",
                severity: "red",
                message:
                    "Calculations for this wire size result in an out of bounds " +
                    "cycle count, Cycle Calculation Maximum (" +
                    CYCLE_MAX.toLocaleString("en-US") +
                    ") Exceeded",
            });
        } else if (cycles && this.cycleTarget && cycles < this.cycleTarget) {
            // LEFT ON THE TARGET, DELIBERATELY, unlike the Duplex warning.
            //
            // The Duplex version of this was changed to a constant 10,000
            // floor on 6,354 readings of evidence. The same change was made
            // here and then reverted, because the five "false alarms" that
            // justified it were produced by the measuring tool and not by this
            // code: the Single readings in dev/eval-single.json carry no
            // spring count, the reference defaults that to 2, and the tool
            // defaulted it to 1 - which puts the whole door on one spring and
            // computes 553 cycles where the reference reports 14,000.
            //
            // With the default corrected this warning fires on NONE of the 523
            // readings, and the reference raises no cycle message on any of
            // them either. So there is nothing here to fix and nothing to
            // measure a rule against: the Single path has never been observed
            // near the boundary from either side. It keeps the rule it has
            // until a reading exists that can tell the two apart.
            found.push({
                id: "cycles-low",
                severity: "red",
                message:
                    "This wire size computes to " +
                    this.cycleLife +
                    ". Low Cycle Life",
            });
        }
    }

    // --- Hi-lift against the drum ----------------------------------------
    // Only reachable with the lift type set to Hi-Lift, which is the only way
    // the input is on screen at all.
    //
    // Under 12" is yellow rather than red: the calculator has a defined
    // answer there, it just is not the one the entry asks for, because
    // anything short of a full 12" is frozen to 0" (see HILIFT_MIN). Over the
    // drum's rating is red - past that the fitted curves leave their measured
    // band entirely.
    //
    // A zero raises nothing. The results are already hidden at that point, so
    // there is nothing on screen to qualify, and an empty field is an input
    // not yet given rather than a wrong one.

    if (this.state.liftType === "Hi-Lift" && this.hiLiftInches > 0) {
        const hiLift = this.hiLiftInches;
        const maxHiLift = this.hiLiftDrumData
            ? this.hiLiftDrumData.maxHiLift
            : null;

        if (maxHiLift && hiLift > maxHiLift) {
            found.push({
                id: "hilift-over-max",
                severity: "red",
                message:
                    "The value you entered (" +
                    hiLift +
                    ") is greater than the maximum allowed(" +
                    maxHiLift +
                    ")",
            });
        } else if (hiLift < HILIFT_MIN) {
            found.push({
                id: "hilift-under-min",
                severity: "yellow",
                message: "Must be " + HILIFT_MIN + " or more",
            });
        }
    }

    // --- Duplex outside its measured ground ------------------------------
    // Yellow, not red: the numbers are the right shape and come from the
    // pair's own stiffness ratios, they are simply not backed by a reading.
    // Saying so beats printing an estimate that looks like a measurement.

    // --- Duplex limits ---------------------------------------------------
    // Everything here comes from the CHOSEN pair, never from the Wire Size
    // dropdown, which Duplex does not show. The two invariants that forbid
    // Duplex reading that control still hold.
    if (this.isDuplex) {
        const pair = this.duplexPair;
        const step = this.duplexStep;

        if (pair && step && this.turnsExact) {
            // Cone capacity. Per spring, so a 4-spring assembly clears it
            // where a 1-spring one does not.
            // FROM THE DISPLAYED FIGURES, both rounded to one decimal, and
            // the per-spring TIPPT rounded BEFORE the multiply. Same rule as
            // duplexCyclesForStep: the reference computes from what it shows.
            //
            // Exact on every case checked. At 676 lb and one spring,
            // round(327.9261, 1) * 6.1 = 2000.19 against the reference's
            // 2000.1900; at 1355 lb and two, round(657.3075 / 2, 1) * 6.1 =
            // 328.7 * 6.1 = 2005.07 against 2005.0700.
            //
            // Using the exact turns instead ran MIP 0.77% low - 6.0533 where
            // the reference shows 6.1 - which is nothing anywhere except at
            // the boundary, and the boundary is the entire purpose of the
            // warning. It missed three readings sitting between 1985 and 2000.
            const perSpring =
                Math.round((this.duplexTipptExact / this.duplexSpringCount) * 10) / 10;
            const shownTurns = Math.round(this.turnsExact * 10) / 10;
            const mip = perSpring * shownTurns;

            if (mip > DUPLEX_MAX_MIP) {
                found.push({
                    id: "duplex-mip-over-max",
                    // 175 single-message responses, all warning.
                    severity: "yellow",
                    message:
                        "Assembly MIP (" +
                        mip.toFixed(4) +
                        ") is over max MIP (" +
                        DUPLEX_MAX_MIP +
                        ") - exceeds cone capacity.",
                });
            }

            const innerMax = DUPLEX_WIRE_MAX[pair.innerId];
            const outerMax = DUPLEX_WIRE_MAX[pair.outerId];

            if (innerMax && step.innerWire > innerMax + 1e-9) {
                found.push({
                    id: "duplex-inner-wire-unsold",
                    // 28 responses where every other message was a known warning, all warning.
                    severity: "yellow",
                    message:
                        "Wire size exceeds " +
                        innerMax +
                        " maximum for the inner spring inside diameter. " +
                        "Service Spring Corporation will not sell springs and " +
                        "Canimex style cones for this combination.",
                });
            }

            if (outerMax && step.outerWire > outerMax + 1e-9) {
                found.push({
                    id: "duplex-outer-wire-unsold",
                    // 155 single-message responses, all warning.
                    severity: "yellow",
                    message:
                        "Wire size exceeds " +
                        outerMax +
                        " maximum for the outer spring inside diameter. " +
                        "Service Spring Corporation will not sell springs and " +
                        "Canimex style cones for this combination.",
                });
            }

            // Cycle life. Exclusive, the same way the Single pair is: a count
            // over the ceiling cannot also be under the target unless the
            // target is itself over the ceiling, and then the ceiling is the
            // message worth showing.
            // ROUNDED, because the reference compares what it DISPLAYS. Its
            // message quotes "cycle life calculation of 9,000.00", a figure
            // already rounded to the nearest thousand, and judges that against
            // the target. Comparing the exact value instead raised this
            // warning on 1014 readings where the reference raised none - an
            // exact 9,960 displays as 10,000 and is not low at all.
            const cycles =
                Math.round(this.duplexCyclesExact / DUPLEX_CYCLE_ROUNDING) *
                DUPLEX_CYCLE_ROUNDING;

            if (cycles > CYCLE_MAX) {
                found.push({
                    id: "duplex-cycles-over-max",
                    // 154 single-message responses, all warning.
                    severity: "yellow",
                    message:
                        "This combination computes to " +
                        Math.round(cycles).toLocaleString("en-US") +
                        " cycles, over the " +
                        CYCLE_MAX.toLocaleString("en-US") +
                        " calculation maximum.",
                });
            } else if (this.duplexCyclesExact && this.duplexCyclesExact < CYCLE_MIN) {
                // A CONSTANT FLOOR, NOT A FRACTION OF THE TARGET - and the
                // long way round to that is worth recording, because the
                // mistake was in the shape of the search and not in the data.
                //
                // This fired when our count came in under THE TARGET, which
                // cost 335 false alarms against 173 agreements: two cries of
                // wolf for every real one. The note that used to be here said
                // the reference's rule was "its own count below about 0.95 of
                // the target", that our count was too coarse to apply it, and
                // that scanning every threshold from 0.70 to 1.05 offered only
                // a choice between missing all of them and 393 false alarms.
                //
                // Every one of those statements was true. The conclusion was
                // still wrong, because 0.70 to 1.05 OF THE TARGET is a family
                // of rules that does not contain the answer, and a search over
                // the wrong family reports "no threshold works" no matter how
                // much data it is given.
                //
                // What the reference actually does, over 6,815 distinct
                // readings, with no exceptions in either direction: it warns
                // when the life it computes falls below 10,000, whatever was
                // asked for. The giveaway was sitting in its own message all
                // along - "less than the 10,000 cycle minimum" names a
                // constant, and it says 10,000 on a 300,000-cycle door too.
                // Three things stop fitting the moment it is read that way:
                //
                //   - every warned reading reports exactly 9,000 cycles, at
                //     door weights from 459 lb to 1,949 lb and across eleven
                //     different rungs. A tolerance on the target cannot
                //     produce one value; a floor at 10,000 can only produce
                //     the one bucket beneath it.
                //   - all 177 of them have a target of 10,000, which is why a
                //     fraction of the target fitted equally well and why the
                //     two rules looked indistinguishable.
                //   - readings that miss a HIGH target are quiet. The same
                //     459 lb door that is warned at a target of 10,000 is
                //     passed without comment at 25,000, 100,000 and 300,000.
                //
                // Measured against this rule our agreement is unchanged at 173
                // and the false alarms go from 335 to 4.
                //
                // STILL YELLOW. The five readings we miss are ones where we
                // compute 10,005 to 10,032 against a reference that reports
                // 9,000, so the boundary is inside our own cycle error and a
                // red verdict would overstate what we know.
                found.push({
                    id: "duplex-cycles-low",
                    severity: "yellow",
                    message:
                        "Computed cycle life of " +
                        cycles.toLocaleString("en-US") +
                        " is below the " +
                        CYCLE_MIN.toLocaleString("en-US") +
                        " cycle minimum. Service Spring's own calculator is " +
                        "likely to reject this pairing - confirm before " +
                        "ordering.",
                });
            }

            // HOW THE THRESHOLD WAS FOUND, having first got this wrong.
            //
            // This warning was implemented against the TARGET - fire when the
            // count is under it - and that agreed on none of its 190 readings
            // while firing on 294 the reference passes. It was withdrawn, and
            // the withdrawal note claimed the warning needed a cycle count
            // more precise than ours. That was wrong: it needed the threshold
            // measured instead of assumed.
            //
            // The reference reports its own cycle count in every response, so
            // the rule can be read straight off 3,070 of them. Sorting by the
            // ratio of reported count to target separates perfectly:
            //
            //   warned   190 readings, highest ratio 0.9000
            //   quiet  2,880 readings, lowest  ratio 0.9600
            //
            // No overlap at all, so the threshold is anywhere in (0.90, 0.96]
            // and the gap is only the thousand-cycle rounding. 0.95 sits in
            // it.
            //
            // IT IS NOT THE SELECTION FRACTION. DUPLEX_ACCEPT_FRACTION is 1.0
            // because that is what reproduces the reference's cycle counts;
            // this is 0.95 because that is what reproduces its warnings. The
            // old code used one number for both, which is why 0.95 looked
            // like the accept fraction for so long - it was the warning
            // threshold all along.

            // THE 96" MESSAGE IS NOT MODELLED, deliberately. The reference
            // also says "Only spring lengths between 0 and 96\" are
            // recommended" - 231 times across the readings here, and 57
            // readings carry it. It looks like a softer version of the
            // warning below and it is tempting to add as a caution.
            //
            // It is not about the spring being quoted. One reading gets it
            // twice while the assembly it returns is 84.25" - comfortably
            // inside 96 - and the number of copies (2, 3, 4, 6) tracks
            // neither the length nor the spring count. The warning below
            // behaves the same way: one reading carries it six times.
            //
            // So these are per-CANDIDATE diagnostics from the reference's own
            // walk up the wire ladder, one per size it considered and threw
            // out, not a statement about the answer. Keying a warning on the
            // final length would fire it on doors the reference is perfectly
            // happy with. Reproducing them properly would mean reproducing
            // its search order and echoing its internal rejections, which is
            // not information the person quoting a door needs.
            //
            // The outer spring is the longer of the two, so it is the one
            // that can run past what is supported.
            if (this.duplexOuterLength > DUPLEX_MAX_SPRING_LENGTH) {
                found.push({
                    id: "duplex-length-unsupported",
                    severity: "red",
                    message:
                        "Only spring lengths between 0 and " +
                        DUPLEX_MAX_SPRING_LENGTH +
                        '" are supported. This assembly needs ' +
                        this.duplexOuterLength +
                        '".',
                });
            }
        }
    }

    if (this.isDuplex && this.duplexExtrapolated) {
        found.push({
            id: "duplex-extrapolated",
            severity: "yellow",
            message:
                "This wire combination has not been checked against the " +
                "reference calculator. Lengths, weights and cycles are " +
                "estimated and may be off by a size.",
        });
    }

    // --- Assembly against the door width ---------------------------------
    // THE MESSAGE NAMES THE DOOR WIDTH, not the assembly length.
    //
    // A note here used to claim the opposite - that the reference printed the
    // assembly length into a sentence reading as though it were the width, and
    // that this app matched it deliberately. A reading settled it: a 348 lb
    // 3-spring door on a 9'0" opening came back with
    //
    //     "Torsion assembly will be too long for a 108 \" wide door!"
    //
    // and 108 is the door width. The assembly is 126.33". So the old claim was
    // wrong, probably from misreading one of the two original readings, where
    // the width was 108" and the assembly 115.40".
    //
    // The reference's own spacing is reproduced, odd as it is - "a 108 " wide
    // door" with a space before the inch mark.

    const width = this.doorWidthTotalInches;

    if (width > 0 && this.assemblyLengthExact > width) {
        found.push({
            id: "assembly-too-long",
            severity: "red",
            message:
                "Torsion assembly will be too long for a " +
                width +
                ' " wide door!',
        });
    }

    // --- Drum ratings ----------------------------------------------------

    const limits = this.drumLimits;

    // Hi-lift drums keep their rating in HILIFT_DRUMS, so a weight over a
    // hi-lift drum's limit raised nothing: 14 readings where the reference
    // says "the weight will be set to the drums maximum weight" and we said
    // nothing, even though duplexEffectiveWeight was already clamping it.
    // Warning and clamping have to come from the same table or the quote
    // silently uses a weight the user never agreed to.
    const hiLimits =
        this.state.liftType === "Hi-Lift" ? HILIFT_DRUMS[this.state.drum] : null;
    const effectiveLimits = hiLimits || limits;

    if (effectiveLimits && effectiveLimits.maxWeight &&
        Number(this.state.weight) > effectiveLimits.maxWeight) {
        found.push({
            id: "weight-over-max",
            severity: "yellow",
            message:
                "The current weight entered is heavier than this drum " +
                "will allow! The maximum weight of this drum is " +
                effectiveLimits.maxWeight +
                " lb.",
        });
    }

    if (limits) {
        const heightInches = this.doorHeightEnteredFeet * 12;

        if (heightInches > limits.maxHeight) {
            found.push({
                id: "height-over-max",
                // 22 single-message responses, all error - the reference
                // treats a door taller than the drum as a hard stop, not a
                // caution, and it clamps the height to build anything at all.
                severity: "red",
                message:
                    "The current height entered is greater than this drum " +
                    "will allow! The maximum height of this drum is " +
                    limits.maxHeight +
                    '".',
            });
        }

    }

    // Worst first. Sort is stable, so within a severity the order above is
    // the order shown.
    const rank = { red: 0, yellow: 1 };

    found.sort((a, b) => rank[a.severity] - rank[b.severity]);

    return found;
}

// Red outranks yellow; null when there is nothing to report.
get warningLevel() {
    if (this.warnings.some((w) => w.severity === "red")) {
        return "red";
    }

    return this.warnings.length ? "yellow" : null;
}

// Applied to every results value. The warnings raised so far are about the
// inputs as a whole rather than one row, so they colour the whole block.
get valueClass() {
    return this.warningLevel
        ? "se-value se-value-" + this.warningLevel
        : "se-value";
}

get warningSuffix() {
    return WARNING_NOTE;
}

toggleWarnings() {
    // Only one panel open at a time.
    this.state.showDrumInfo = false;
    this.state.showWarnings = !this.state.showWarnings;
}

closeWarnings() {
    this.state.showWarnings = false;
}

get drumInfo() {
    return DRUM_INFO[this.state.drum] || null;
}

// The panel opens whether or not a drum is chosen, so it can say what it
// wants from the user instead of the symbol simply not being there.
get drumInfoTitle() {
    return this.state.drum || "No drum selected!";
}

// Only used when there are no specification rows to show.
get drumInfoMessage() {
    if (!this.state.drum) {
        return "Please select a drum on the right and tap this again to " +
               "see details about the selected drum.";
    }
    return "No specifications are available for this drum yet.";
}

get drumInfoLabel() {
    return this.state.drum
        ? "Specifications for " + this.state.drum
        : "No drum selected";
}

toggleDrumInfo() {
    // Only one panel open at a time.
    this.state.showWarnings = false;
    this.state.showDrumInfo = !this.state.showDrumInfo;
}

closeDrumInfo() {
    this.state.showDrumInfo = false;
}

    clearAll() {
        // Mutate in place rather than reassigning this.state - replacing the
        // useState proxy would detach the component from its reactivity.
        Object.assign(this.state, defaultState());
    }

    // WHAT GOES TO THE SERVER: the SPECIFICATION, never the price.
    //
    // /spring-calculator is public, so anything this page posts is whatever its
    // sender chose. The controller recomputes every chargeable figure from the
    // geometry below using its own constants, which it reads out of this file
    // so the two cannot drift. A sender can therefore ask for a spring the
    // calculator would not have recommended, but not for one at a price it did
    // not earn.
    //
    // Duplex diameters come from duplexPair, which has already resolved the
    // aliases, so a Raynor pair is priced as the 2 5/8" inside 5 1/4" it is
    // engineered as - the same resolution the price rows use.
    get cartSpec() {
        const springs = [];

        if (this.isDuplex) {
            const step = this.duplexStep;
            const pair = this.duplexPair;

            if (step && pair) {
                springs.push({
                    role: "Outer", wire: step.outerWire,
                    id: pair.outerId, length: this.duplexOuterLength,
                });
                springs.push({
                    role: "Inner", wire: step.innerWire,
                    id: pair.innerId, length: this.duplexInnerLength,
                });
            }
        } else {
            springs.push({
                role: "Spring", wire: this.wireSizeNumber,
                id: this.springIdNumber, length: this.springLength,
            });
        }

        return {
            assembly: this.state.assembly,
            springs: Number(this.state.springs) || 0,
            drum: this.state.drum,
            cycles: this.state.cycles,
            doorWeight: this.state.weight,
            doorHeight: `${this.state.doorHeightFeet}' ${this.state.doorHeightInches || 0}"`,
            springsSpec: springs,
        };
    }

    async addToCart() {
        if (!this.resultsVisible || this.state.cartBusy) {
            return;
        }

        this.state.cartBusy = true;
        this.state.cartError = "";

        try {
            const result = await rpc("/spring-calculator/add-to-cart", {
                spec: this.cartSpec,
            });

            // The controller answers with a message rather than an exception
            // for anything it will not build, so it can be shown as it is.
            if (result && result.error) {
                this.state.cartError = result.error;

                return;
            }

            window.location = "/shop/cart";
        } catch {
            this.state.cartError =
                "Could not reach the cart just now. Please try again, or call us to order.";
        } finally {
            this.state.cartBusy = false;
        }
    }
}

// TWO PLACES, ONE COMPONENT.
//
//   actions            the backend app, reached from the Spring Engineering
//                      menu as an ir.actions.client.
//   public_components  the public website page at /spring-calculator, mounted
//                      by <owl-component name="spring_engineering.calculator"/>
//                      in the page template.
//
// Registering the same class twice rather than wrapping or subclassing it
// means the website and the backend cannot drift apart: a fix to the ladder,
// a price or a warning lands in both at once. The component takes no props
// and reads nothing from the action, so neither registry needs an adapter.
registry
    .category("actions")
    .add("spring_engineering.calculator", SpringEngineering);

registry
    .category("public_components")
    .add("spring_engineering.calculator", SpringEngineering);