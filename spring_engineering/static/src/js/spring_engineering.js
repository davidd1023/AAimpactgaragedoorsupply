/** @odoo-module **/

import { Component, useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

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
        catalog: true,
        reff: hl800REff,
        multiplier: hl800Multiplier,
    },
    // Catalog-built. See the HL575_* block above for how it differs from the
    // reverse-engineered drums, and why.
    "CANIMEX/TF 575-120": {
        maxHiLift: 120,
        catalog: true,
        reff: hl575REff,
        multiplier: hl575Multiplier,
    },
    "CANIMEX/TF 525-54HL": {
        maxHiLift: 54,
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
const WIRE_SIZES = [
    0.125, 0.135, 0.142, 0.1483, 0.1562, 0.162, 0.17, 0.177, 0.1875, 0.192,
    0.2, 0.207, 0.2187, 0.2253, 0.2343, 0.2437, 0.25, 0.2625, 0.273, 0.283,
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
            { outerWire: 0.2625, innerWire: 0.2253, K: 2003.0, n: 129, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 0.413, bonus: 1.25 }, { upTo: 0.435, bonus: 3.25 }, { upTo: 0.583, bonus: 1.25 }, { upTo: 0.636, bonus: 2.25 }, { upTo: 0.766, bonus: 1 }, { upTo: 0.821, bonus: 2.25 }, { upTo: 0.86, bonus: 1 }, { upTo: 0.882, bonus: 2.25 }, { upTo: 0.911, bonus: 1 }, { upTo: 0.974, bonus: 2.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.256, bonus: 2.25 }, { upTo: 0.278, bonus: 1.25 }, { upTo: 0.288, bonus: 2.25 }, { upTo: 0.414, bonus: 1.25 }, { upTo: 0.578, bonus: 2.25 }, { upTo: 0.639, bonus: 1.25 }, { upTo: 0.744, bonus: 2.25 }, { upTo: 0.796, bonus: 1.25 }, { upTo: 0.949, bonus: 2.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 0.054, bonus: 0.25 }, { upTo: 0.121, bonus: 1.25 }, { upTo: 0.199, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] }, long: { from: 25.5, split: 0.065, above: 2.25 } },
            { outerWire: 0.273, innerWire: 0.2253, K: 2230.7, n: 62, byCount: { 2: [{ upTo: 0.4, bonus: 0 }, { upTo: 0.498, bonus: 1.25 }, { upTo: 0.572, bonus: 0 }, { upTo: 0.681, bonus: 1.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 1.25 }], 4: [{ upTo: 0.554, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.283, innerWire: 0.2253, K: 2426.1, n: 67, byCount: { 2: [{ upTo: 0.89, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 0.25 }], 4: [{ upTo: 0.809, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.283, innerWire: 0.2343, K: 2688.8, n: 31, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 0.649, bonus: 1.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.289, innerWire: 0.2343, K: 2848.7, n: 59, byCount: { 1: [{ upTo: 0.711, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.642, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.671, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 0.431, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.295, innerWire: 0.2343, K: 2949.1, n: 47, byCount: { 1: [{ upTo: 1, bonus: 0 }], 2: [{ upTo: 1, bonus: 0 }], 3: [{ upTo: 0.809, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 0.25 }] } },
            { outerWire: 0.295, innerWire: 0.2437, K: 3282.3, n: 38, byCount: { 3: [{ upTo: 0.292, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 0.25 }] } },
            { outerWire: 0.3065, innerWire: 0.2437, K: 3581.0, n: 52, byCount: { 1: [{ upTo: 1, bonus: 0 }], 2: [{ upTo: 0.818, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.751, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 0.667, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3065, innerWire: 0.25, K: 3859.8, n: 24, byCount: { 3: [{ upTo: 0.469, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 0.25 }] } },
            { outerWire: 0.3125, innerWire: 0.25, K: 4058.0, n: 36, byCount: { 3: [{ upTo: 0.68, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 0.702, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3125, innerWire: 0.2625, K: 4520.9, n: 8, byCount: { 3: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3195, innerWire: 0.2625, K: 4807.2, n: 28, byCount: { 1: [{ upTo: 0.37, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.319, bonus: 0 }, { upTo: 1, bonus: 1.25 }], 3: [{ upTo: 0.31, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 0.517, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.331, innerWire: 0.2625, K: 5166.1, n: 47, byCount: { 1: [{ upTo: 0.717, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.739, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.731, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.331, innerWire: 0.273, K: 5798.7, n: 63, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 0.481, bonus: 1.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.229, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3437, innerWire: 0.273, K: 6325.9, n: 34, byCount: { 1: [{ upTo: 0.65, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.697, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.393, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 0.25 }] } },
            { outerWire: 0.3437, innerWire: 0.283, K: 6932.5, n: 56, byCount: { 1: [{ upTo: 0.207, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.23, bonus: 0 }, { upTo: 0.534, bonus: 1.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.366, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3625, innerWire: 0.283, K: 7484.7, n: 40, byCount: { 1: [{ upTo: 0.876, bonus: 0 }, { upTo: 0.943, bonus: 1 }, { upTo: 1, bonus: 0 }], 2: [{ upTo: 0.844, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.883, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3625, innerWire: 0.289, K: 8296.5, n: 57, byCount: { 3: [{ upTo: 0.565, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3625, innerWire: 0.295, K: 8783.4, n: 23, byCount: { 1: [{ upTo: 0.271, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 1.25 }], 4: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.375, innerWire: 0.295, K: 9177.8, n: 68, byCount: { 1: [{ upTo: 0.71, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.691, bonus: 0 }, { upTo: 0.833, bonus: 1 }, { upTo: 1, bonus: 0 }], 3: [{ upTo: 0.736, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.375, innerWire: 0.3065, K: 10478.6, n: 48, byCount: { 1: [{ upTo: 0.061, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.069, bonus: 0 }, { upTo: 0.316, bonus: 1.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.075, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3938, innerWire: 0.3065, K: 11082.4, n: 61, byCount: { 1: [{ upTo: 0.149, bonus: 0 }, { upTo: 0.261, bonus: -1 }, { upTo: 1, bonus: 0 }], 2: [{ upTo: 0.227, bonus: -1 }, { upTo: 1, bonus: 0 }], 3: [{ upTo: 0.032, bonus: -0.75 }, { upTo: 1, bonus: 0.25 }] } },
            { outerWire: 0.3938, innerWire: 0.3125, K: 12199.7, n: 58, byCount: { 3: [{ upTo: 0.685, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.3938, innerWire: 0.3195, K: 13120.9, n: 35, byCount: { 1: [{ upTo: 0.277, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.4062, innerWire: 0.3195, K: 13594.4, n: 50, byCount: { 1: [{ upTo: 0.657, bonus: 0 }, { upTo: 1, bonus: 1 }], 2: [{ upTo: 0.728, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.771, bonus: 0.25 }, { upTo: 0.829, bonus: 1.25 }, { upTo: 0.875, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.4062, innerWire: 0.331, K: 15433.0, n: 61, byCount: { 1: [{ upTo: 0.942, bonus: 1 }, { upTo: 1, bonus: 2 }], 2: [{ upTo: 0.219, bonus: 1.25 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 0.883, bonus: 1.25 }, { upTo: 1, bonus: 2.25 }] } },
            { outerWire: 0.4218, innerWire: 0.331, K: 16190.5, n: 34, byCount: { 2: [{ upTo: 1, bonus: 0 }], 3: [{ upTo: 0.887, bonus: 0.25 }, { upTo: 1, bonus: 1.25 }] } },
            { outerWire: 0.4218, innerWire: 0.3437, K: 18569.5, n: 40, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 1, bonus: 1 }], 3: [{ upTo: 0.802, bonus: 1.25 }, { upTo: 1, bonus: 2.25 }] } },
            { outerWire: 0.4305, innerWire: 0.3437, K: 19477.8, n: 48, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 0.325, bonus: 0 }, { upTo: 1, bonus: 1 }], 3: [{ upTo: 1, bonus: 0.25 }] } },
            { outerWire: 0.4305, innerWire: 0.3625, K: 22027.8, n: 10, byCount: { 1: [{ upTo: 1, bonus: 2 }], 2: [{ upTo: 0.924, bonus: 2.25 }, { upTo: 1, bonus: 3.25 }] } },
            { outerWire: 0.4375, innerWire: 0.3625, K: 23018.6, n: 38, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 0.103, bonus: 1.25 }, { upTo: 0.348, bonus: 1 }, { upTo: 1, bonus: 2.25 }] } },
            { outerWire: 0.4531, innerWire: 0.3625, K: 25305.9, n: 22, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 0.264, bonus: 0 }, { upTo: 1, bonus: 1 }] } },
            { outerWire: 0.4531, innerWire: 0.375, K: 27632.5, n: 8, byCount: { 1: [{ upTo: 1, bonus: 1 }], 2: [{ upTo: 1, bonus: 2.25 }] } },
            { outerWire: 0.4687, innerWire: 0.375, K: 30169.8, n: 8, byCount: { 1: [{ upTo: 1, bonus: 1 }] } },
            { outerWire: 0.49, innerWire: 0.3938, K: 37971.3, n: 8, byCount: { 1: [{ upTo: 1, bonus: 1 }] } },
            { outerWire: 0.5, innerWire: 0.3938, K: 38321.7, n: 8 },
            { outerWire: 0.5312, innerWire: 0.4062, K: 44642.9, n: 8, byCount: { 1: [{ upTo: 1, bonus: -1 }] } },
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
const DUPLEX_ACCEPT_FRACTION = 0.95;

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

    return (
        (springs *
            (divider(step.outerWire, pair.outerId) +
                divider(step.innerWire, pair.innerId))) /
        tippt
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
    // this one depends on the active length. Measured: 11 readings from active
    // 30.7 to 38.2 at +2.25, against 9 at active 14.5-15.8 behaving otherwise,
    // with the boundary bracketed to (25.290, 25.807] by a 500/490 lb pair.
    if (regime && regime.long && activeLength >= regime.long.from) {
        return frac < regime.long.split
            ? whole + 1.25
            : whole + regime.long.above;
    }

    // DERIVED BANDS, per rung AND per spring count - see dev/derive.mjs.
    //
    // One rule per rung is not enough: 1, 2, 3 and 4 springs sit on different
    // quarter-inch grids and take different bonus values, so the bonus is a
    // piecewise-constant function of frac for each (rung, count) pair. Bands
    // exist only where readings cover them and only where plain rounding is
    // already wrong; everything else falls through to round().
    const bands = regime && regime.byCount && regime.byCount[springs];

    if (bands) {
        for (const band of bands) {
            if (frac < band.upTo) {
                return whole + band.bonus;
            }
        }
    }

    return Math.round(activeLength);
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
    "CANIMEX/TF D400-96": { maxHeight: 96, maxWeight: 530, maxCable: '1/8"' },
    "CANIMEX/TF D400-144": { maxHeight: 144, maxWeight: 750, maxCable: '5/32"' },
    "CANIMEX/TF D525-216": { maxHeight: 216, maxWeight: 1500, maxCable: '3/16"' },
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

function duplexPairBuildable(pair, outerWire, innerWire) {
    if (pair.innerId + 2 * innerWire >= pair.outerId) {
        return false;
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
//   assembly = springs * (springLength + turns * wire) + ASSEMBLY_HARDWARE
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
const ASSEMBLY_HARDWARE = 24;

// The ceiling on the cycle formula itself. Past this the reference stops
// trusting its own answer rather than reporting a larger number, so this is a
// bound on the CALCULATION, not on any spring.
const CYCLE_MAX = 350000;

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

get turns() {
    return Math.round(this.turnsExact * 100) / 100;
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
    // Display only. Nothing computes from this - see springLengthExact.
    return Math.round(this.tipptExact * 100) / 100;
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

get springLength() {
    return Math.round(this.springLengthExact * 100) / 100;
}

get springWeight() {
    // Steel weight of one spring, in lb. See STEEL_DENSITY above.
    // `meanDiameter` is springID + wire, which is exactly the coil diameter
    // the wire follows.
    if (!this.springLengthExact || !this.wireSizeNumber) {
        return 0;
    }

    const volume =
        ((Math.PI ** 2) / 4) *
        this.wireSizeNumber *
        this.meanDiameter *
        this.springLengthExact;

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
    const limits = DRUM_LIMITS[this.state.drum];

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
    // A generated rung's K is estimated as S times the catalogue's own median
    // K/S, which is a far better extrapolation than the kSlope line it
    // replaces - that line ran 8.5% low on the first rung past the table.
    // duplexExtrapolated still reports when one is in use.
    const ratios = pair.calibration.map(
        (c) =>
            c.K /
            (2 *
                (divider(c.outerWire, pair.outerId) +
                    divider(c.innerWire, pair.innerId)))
    );
    const medianRatio = ratios.slice().sort((x, y) => x - y)[
        Math.floor(ratios.length / 2)
    ];
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
                K: S * medianRatio,
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
        .filter((c) => duplexPairBuildable(pair, c.outerWire, c.innerWire))
        .sort((a, b) => a.S - b.S);

    // Never return nothing - if the cycle-rating limit excludes everything,
    // fall back to the softest BUILDABLE combination rather than leaving the
    // caller empty. The buildability gate is not negotiable here: a pair that
    // cannot be wound is worse than no suggestion.
    if (all.length) {
        return all;
    }

    const buildable = out
        .filter((c) => duplexPairBuildable(pair, c.outerWire, c.innerWire))
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

// Cycle life of the set. K is the spring's body length times TIPPT, so the
// body is K/TIPPT and the rate follows; the rest is the standard cycle
// formula on the inner spring, which is the one the reference reports.
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

        return this.duplexSpringCount * woundPerSpring + ASSEMBLY_HARDWARE;
    }

    if (!this.springLengthExact) {
        return 0;
    }

    const woundPerSpring =
        this.springLengthExact + this.turnsExact * this.wireSizeNumber;

    return this.state.springs * woundPerSpring + ASSEMBLY_HARDWARE;
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

    if (limits) {
        const heightInches = this.doorHeightTotalFeet * 12;

        if (heightInches > limits.maxHeight) {
            found.push({
                id: "height-over-max",
                severity: "yellow",
                message:
                    "The current height entered is greater than this drum " +
                    "will allow! The maximum height of this drum is " +
                    limits.maxHeight +
                    '".',
            });
        }

        if (Number(this.state.weight) > limits.maxWeight) {
            found.push({
                id: "weight-over-max",
                severity: "yellow",
                message:
                    "The current weight entered is heavier than this drum " +
                    "will allow! The maximum weight of this drum is " +
                    limits.maxWeight +
                    " lb.",
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
}

registry
    .category("actions")
    .add("spring_engineering.calculator", SpringEngineering);