/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
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
// Built from the manufacturer's own published tables (Canimex Cable Drum
// Catalog, D575-120, "MULTIPLIER FOR HIGH-LIFT DRUM"), not reverse-engineered
// from calculator output. 861 printed multipliers: door heights 6'0"-22'0" in
// 6" steps, hi-lift 0-120" in 3" steps.
//
// The catalog publishes H.M.A. (the effective radius) alongside MULTI and
// TURNS, and MULTI * TURNS = H.M.A. exactly - the same relationship the
// 525-54HL was found to obey. H.M.A. follows the identical flat-spiral law,
// here with a base radius of 2.969" and the same 5/16" cable pitch:
//
//     rEff(HL) = sqrt(2.969^2 + (0.3125/pi) * HL)
//
// which reproduces all 41 printed H.M.A. values to 0.00005, i.e. exactly the
// 4 decimals the catalog prints.
//
// CAVEAT - this drum is NOT calibrated against the same reference calculator
// as the other drums. Spot-checked on D525-54, the catalog and that
// calculator disagree by 0.01-0.07%, growing with hi-lift, because the
// calculator uses a slightly larger pitch constant. The catalog is the
// manufacturer's authoritative data and 0.05% on a multiplier is not
// engineering-significant, but the two sources are not identical. This is a
// deliberate, temporary choice: ship from the catalog now, re-fit against the
// reference calculator later.
// Two sets of spiral constants, because the catalog and the reference
// calculator genuinely disagree.
//
// NODE_* are the catalog's own (r0 = 2.969", pitch exactly 5/16"). They fix
// where the interpolation columns below sit, so they are part of how the
// published surface is indexed and must not be retuned.
//
// HL575_A/B are the reference calculator's, recovered from its 100 lb cycle
// counts. The implied pitch is 0.313097" - the same constant the 525-54HL
// turned out to use, to seven figures. So the calculator applies one pitch
// across drums and the catalog's clean 5/16" is the outlier. These drive
// rEff, and therefore turns and cycle life.
const HL575_NODE_A = 8.814961;     // catalog r0^2
const HL575_NODE_B = 0.099471839;  // catalog (5/16")/pi
const HL575_A = 8.8176917;         // calculator r0^2, r0 = 2.96946"
const HL575_B = 0.099661791;       // calculator pitch/pi, pitch = 0.313097"

// Correction onto the reference calculator, one curve per measured hi-lift
// column rather than a single global formula.
//
// The first attempt fitted a full quadratic in (hi-lift, 1/height) to the
// whole surface and stalled: 0.0272% worst, 0.0068% median over 58 reference
// points. The offset's shape ACROSS height changes with hi-lift - flat and
// within the catalog's own rounding at 24" (+0.012% to -0.004%, pure
// scatter), steep at 72" (+0.234% at 6' falling to +0.048% at 18') - and no
// low-order product form covers both. Fitting a curve per column and
// interpolating those, the same structure the surface itself uses, gives
// 0.0087% worst and 0.0013% median over 65 points: worst cut by a third,
// median by five times.
//
// Each row is [hiLift, a, b, c, d] for
//     offset = a + b*(10/H) + c*(10/H)^2 + d*(10/H)^3
// with the term count per column chosen by leave-one-out, so a thinly
// sampled column cannot overfit. The 24" column resolves to a single
// constant because its offset is genuinely flat - the residual there is the
// catalog's 4-decimal rounding, which at a multiplier of 0.3 to 0.5 is
// itself 0.01 to 0.017%, so that column cannot be improved by more runs.
const HL575_OFFSET_COLUMNS = [
        [  0, -0.0002652091,  0.0000000000,  0.0000000000,  0.0000000000],
        [ 12, -0.0003500735,  0.0005080514, -0.0002187039,  0.0000000000],
        [ 24,  0.0000470968,  0.0000000000,  0.0000000000,  0.0000000000],
        [ 36, -0.0000285671,  0.0002564019,  0.0000000000,  0.0000000000],
        [ 48,  0.0004627047, -0.0006666301,  0.0005494695,  0.0000000000],
        [ 60,  0.0022910666, -0.0064359252,  0.0063270691, -0.0017123162],
        [ 72,  0.0012969913, -0.0024405486,  0.0018323139,  0.0000000000],
        [ 84,  0.0005465707, -0.0010155875,  0.0014308454,  0.0000000000],
        [ 90, -0.0015614725,  0.0070670816, -0.0080342972,  0.0036354436],
        [ 96, -0.0003655542,  0.0015779125,  0.0000000000,  0.0000000000],
        [108, -0.0003333715,  0.0016686279,  0.0000000000,  0.0000000000],
        [120,  0.0002946135,  0.0003244492,  0.0010317381,  0.0000000000],
];

// One row per printed hi-lift column:
//   [hiLift, lowest door height the catalog publishes for it, a, b, c, d, e, f]
// where the six coefficients give the multiplier across door height as
//     multiplier = a*(H/10) + b + c*(10/H) + d*(10/H)^2 + e*(10/H)^3 + f*(10/H)^4
// The 10 is only a scale factor to keep the basis well conditioned over the
// 6-22 ft span; without it the inverse powers are nearly collinear and the
// coefficients stop varying smoothly from column to column.
//
// Between columns the six coefficients are interpolated with a local cubic in
// rEff (not in hi-lift - rEff is the drum's own coordinate, and the columns
// are evenly spaced in neither). Accuracy against all 861 published values:
// worst 0.000067, mean 0.000020, with 830 of 861 reproducing exactly at the
// catalog's 4 decimals. Dropping 10 of the 41 columns and predicting them
// still gives a worst case of 0.00012, so the interpolation is not merely
// memorising the nodes.
const HL575_COLUMNS = [
        [  0,   6.0, -0.04908332,  0.21545915,  0.08907425,  0.28246942, -0.13295727,  0.02197211],
        [  3,   6.0,  0.05247068, -0.23290194,  0.87621555, -0.39545862,  0.14736898, -0.02443022],
        [  6,   6.0, -0.02830941,  0.11880087,  0.27947545,  0.10555008, -0.06680811,  0.01088577],
        [  9,   6.0, -0.05080358,  0.22591582,  0.08963201,  0.27020224, -0.14255157,  0.02351969],
        [ 12,   6.0, -0.03053611,  0.14087547,  0.23662070,  0.14744295, -0.09895074,  0.01686382],
        [ 15,   6.0,  0.03053796, -0.13459129,  0.73071602, -0.28479695,  0.07996094, -0.01303493],
        [ 18,   6.0, -0.00602366,  0.03229889,  0.43980265, -0.03468277, -0.03190356,  0.00572225],
        [ 21,   6.0, -0.00483884,  0.01880993,  0.48326834, -0.08523881, -0.01241197,  0.00212309],
        [ 24,   6.0, -0.02031785,  0.09434278,  0.34852021,  0.03270880, -0.06864867,  0.01153954],
        [ 27,   6.0, -0.01760642,  0.07837300,  0.39170570, -0.01670203, -0.04860099,  0.00743261],
        [ 30,   6.0, -0.00460012,  0.02007677,  0.49958906, -0.11119458, -0.01470291,  0.00195368],
        [ 33,   6.0,  0.00313767, -0.01214117,  0.55830234, -0.16149386,  0.00017621, -0.00039771],
        [ 36,   6.0, -0.01324831,  0.06491068,  0.42295925, -0.04277098, -0.05718861,  0.00936724],
        [ 39,   6.0, -0.00467343,  0.02467667,  0.50301306, -0.11710532, -0.03003231,  0.00462703],
        [ 42,   6.0, -0.00176255,  0.01058186,  0.53626878, -0.15111645, -0.01950033,  0.00246772],
        [ 45,   6.0,  0.00489677, -0.02437835,  0.61361207, -0.22932374,  0.01219819, -0.00361719],
        [ 48,   6.0,  0.00152741, -0.00692345,  0.58501852, -0.20446765, -0.00429083, -0.00107517],
        [ 51,   6.0,  0.00007221,  0.00122392,  0.57396323, -0.19515248, -0.01439979,  0.00047670],
        [ 54,   6.0, -0.00874261,  0.04319300,  0.50311855, -0.13517201, -0.04508624,  0.00518822],
        [ 57,   6.0, -0.00297982,  0.01500899,  0.56211340, -0.19088402, -0.02584242,  0.00145146],
        [ 60,   6.0,  0.00282036, -0.01458455,  0.62659505, -0.25421193, -0.00221831, -0.00322902],
        [ 63,   6.0,  0.00333835, -0.01798687,  0.64198637, -0.27465381,  0.00414919, -0.00544059],
        [ 66,   6.0, -0.00136412,  0.00633613,  0.59863882, -0.23335317, -0.02130834, -0.00134663],
        [ 69,   6.0, -0.00023366,  0.00045403,  0.61636496, -0.25231275, -0.01759680, -0.00287153],
        [ 72,   6.0,  0.00155153, -0.00975642,  0.64480530, -0.28375840, -0.00704728, -0.00587105],
        [ 75,   6.5, -0.00400770,  0.02252016,  0.57936486, -0.21599989, -0.04657600,  0.00071517],
        [ 78,   6.5, -0.00063511,  0.00363778,  0.62472065, -0.26171723, -0.03099605, -0.00296704],
        [ 81,   7.0, -0.00247566,  0.01055209,  0.62374393, -0.27113683, -0.02646806, -0.00621052],
        [ 84,   7.0, -0.00037089,  0.00139883,  0.64291446, -0.28446073, -0.02960353, -0.00596627],
        [ 87,   7.5,  0.00288326, -0.01632672,  0.68505169, -0.32676530, -0.01506863, -0.00999796],
        [ 90,   7.5,  0.00083454, -0.00506568,  0.66822109, -0.31344451, -0.02453805, -0.01048131],
        [ 93,   8.0, -0.00738514,  0.04800700,  0.53977213, -0.15438037, -0.12651347,  0.01175731],
        [ 96,   8.0,  0.00233500, -0.01475022,  0.70403465, -0.35738160, -0.00906522, -0.01828404],
        [ 99,   8.5,  0.00359593, -0.02489564,  0.73966597, -0.40561590,  0.01697156, -0.02729389],
        [102,   8.5,  0.00621590, -0.04098074,  0.78419808, -0.45866795,  0.04282730, -0.03570378],
        [105,   9.0,  0.00423253, -0.03005054,  0.76802466, -0.44724036,  0.03738246, -0.03906855],
        [108,   9.0,  0.01508576, -0.10801281,  0.99176911, -0.75080136,  0.23320655, -0.09265520],
        [111,   9.5, -0.00364474,  0.02409077,  0.63160468, -0.26066928, -0.09851435, -0.00916108],
        [114,   9.5, -0.00716313,  0.05141709,  0.55483807, -0.14705037, -0.18406135,  0.01080518],
        [117,  10.0, -0.00874001,  0.06255118,  0.52888896, -0.10853274, -0.21707263,  0.01671791],
        [120,  10.0,  0.01017702, -0.08121440,  0.96352091, -0.74395766,  0.23550852, -0.11543010],
];

const HL575_MAX = 120;             // last printed hi-lift column

// The reference calculator freezes everything below a full 12" of hi-lift to
// the 0" row - confirmed on this drum (7'0"/6" returns 0.5886, the 7'0"/0"
// value) and on the 525-54HL, where 6", 8", 9", 10" and 11" all returned
// bit-identical output. The catalog does NOT do this: it prints real entries
// at 3", 6" and 9". The clamp is a property of the calculator rather than of
// the drum, so it applies to catalog-built drums too.
function hl575Applied(hiLiftInches) {
    const hl = Number(hiLiftInches) || 0;

    // Below 12" and ABOVE the maximum both fall back to the 0" row - above
    // the maximum it is a fallback, not a clamp. Measured on this drum at
    // 125", which returns the 0" cycle count of 3762 rather than the 120"
    // one, and on the D800-120, which behaves the same way.
    if (hl < HILIFT_MIN || hl > HL575_MAX) {
        return 0;
    }

    return hl;
}

function hl575REff(hiLiftInches) {
    return Math.sqrt(HL575_A + HL575_B * hl575Applied(hiLiftInches));
}

// Where a hi-lift sits along the catalog's own radius axis - the coordinate
// the interpolation columns are keyed by. Deliberately the catalog constants,
// not the calculator's.
function hl575Node(hiLift) {
    return Math.sqrt(HL575_NODE_A + HL575_NODE_B * hiLift);
}

function hl575Correction(heightFeet, hiLift) {
    const u = hl575Node(hiLift);

    let nearest = 0;

    for (let i = 1; i < HL575_OFFSET_COLUMNS.length; i++) {
        if (
            Math.abs(hl575Node(HL575_OFFSET_COLUMNS[i][0]) - u) <
            Math.abs(hl575Node(HL575_OFFSET_COLUMNS[nearest][0]) - u)
        ) {
            nearest = i;
        }
    }

    const start = Math.max(
        0,
        Math.min(nearest - 1, HL575_OFFSET_COLUMNS.length - 3)
    );
    const window = HL575_OFFSET_COLUMNS.slice(start, start + 3);
    const nodes = window.map((row) => hl575Node(row[0]));

    const inv = 10 / heightFeet;
    const shape = [1, inv, inv ** 2, inv ** 3];

    let offset = 0;

    for (let a = 0; a < 4; a++) {
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

    return 1 + offset;
}

function hl575Multiplier(heightFeet, hiLiftInches) {
    const height = Number(heightFeet) || 0;

    if (height <= 0) {
        return 0;
    }

    const applied = hl575Applied(hiLiftInches);
    const u = hl575Node(applied);

    // Four nearest columns, clamped to stay inside the table.
    let nearest = 0;

    for (let i = 1; i < HL575_COLUMNS.length; i++) {
        if (
            Math.abs(hl575Node(HL575_COLUMNS[i][0]) - u) <
            Math.abs(hl575Node(HL575_COLUMNS[nearest][0]) - u)
        ) {
            nearest = i;
        }
    }

    const start = Math.max(0, Math.min(nearest - 1, HL575_COLUMNS.length - 4));
    const window = HL575_COLUMNS.slice(start, start + 4);
    const nodes = window.map((row) => hl575Node(row[0]));

    const inv = 10 / height;
    const basis = [height / 10, 1, inv, inv ** 2, inv ** 3, inv ** 4];

    let multiplier = 0;

    for (let a = 0; a < 6; a++) {
        let value = 0;

        for (let j = 0; j < window.length; j++) {
            let weight = 1;

            for (let m = 0; m < nodes.length; m++) {
                if (m !== j) {
                    weight *= (u - nodes[m]) / (nodes[j] - nodes[m]);
                }
            }

            value += weight * window[j][a + 2];
        }

        multiplier += value * basis[a];
    }

    return multiplier * hl575Correction(height, applied);
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
// column rather than a single global formula.
//
// A global polynomial in (hi-lift, 1/height) was tried and stalls at 0.031%:
// the offset's SHAPE across height changes with hi-lift - nearly flat at 18"
// (+0.016% from 7' to 20') and steep at 120" (+0.21% at 10' down to +0.060%
// at 28') - which no low-order product form captures. Fitting a curve per
// column and interpolating those, exactly as the surface itself is built,
// reaches 0.0066% worst and 0.0011% median over 57 reference points.
//
// Each row is [hiLift, a, b, c, d] for
//     offset = a + b*(10/H) + c*(10/H)^2 + d*(10/H)^3
// with the term count per column chosen by leave-one-out, so a column with
// few measured heights cannot overfit. The 0" row is a single anchor.
//
// Every measured point is included. 11'0" at 120" was briefly suspected of
// being a mis-key, because dropping it improves that column's fit from
// 1.8e-04 to 5.5e-05. It was re-run and confirmed. The explanation is the
// catalog, not the datum: at 120" the multipliers run 0.24 to 0.38, where
// the catalog's 4-decimal rounding is +/-5e-05 - which is +/-1.3e-04 to
// +/-2e-04 once divided through into the offset. That column is at the
// catalog's precision floor, and no number of extra runs will move it.
const HL800_OFFSET_COLUMNS = [
        [  0, -0.0001294229,  0.0000000000,  0.0000000000,  0.0000000000],
        [ 18,  0.0001615367,  0.0000000000,  0.0000000000,  0.0000000000],
        [ 36,  0.0001641541,  0.0001093716,  0.0000000000,  0.0000000000],
        [ 48,  0.0003029403, -0.0000527805,  0.0001547716,  0.0000000000],
        [ 66,  0.0004732692, -0.0005552553,  0.0006765056,  0.0000000000],
        [ 78,  0.0008421350, -0.0017933223,  0.0017675247,  0.0000000000],
        [ 96, -0.0004523175,  0.0045373726, -0.0070243310,  0.0040413309],
        [108,  0.0008287370, -0.0016324146,  0.0023095161,  0.0000000000],
        [120,  0.0011691323, -0.0028491072,  0.0037063837,  0.0000000000],
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
    const shape = [1, inv, inv ** 2, inv ** 3];

    let offset = 0;

    for (let a = 0; a < 4; a++) {
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
const HILIFT_DRUMS = {
    "CANIMEX/TF D800-120": {
        catalog: true,
        reff: hl800REff,
        multiplier: hl800Multiplier,
    },
    // Catalog-built. See the HL575_* block above for how it differs from the
    // reverse-engineered drums, and why.
    "CANIMEX/TF 575-120": {
        catalog: true,
        reff: hl575REff,
        multiplier: hl575Multiplier,
    },
    "CANIMEX/TF 525-54HL": {
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

export class SpringEngineering extends Component {

    static template = "spring_engineering.Calculator";

    setup() {
        this.state = useState({
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
            wireSize: '0.125"',


        });
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

    return drumTurns(this.drumData, this.doorHeightTotalFeet);
}

get turns() {
    return Math.round(this.turnsExact * 100) / 100;
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
    // The only input the reference calculator refuses is a hi-lift of zero or
    // blank, which hides the results rows entirely. Everything else it
    // computes and shows - including past the drum's published range, where
    // the multiplier crosses zero and goes NEGATIVE.
    //
    // Measured on the D800-120: a 7'0" door is 84", so 96" of hi-lift is past
    // its limit, and the reference returns -0.000230 there, -0.173892 at 108"
    // and -0.362278 at 120". The surface reaches those on its own by
    // extrapolating its own columns, landing within 0.0005 at 96" and 108"
    // and 0.005 at 120".
    //
    // Out there the numbers are not engineering answers - negative spring
    // lengths and negative turns - but they are what the reference produces,
    // and matching it is the point.
    if (this.hiLiftDrumData) {
        return this.hiLiftInches > 0;
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

get cycleLife() {
    const torque = this.springTorque;

    if (!torque || !this.wireSizeNumber) {
        return 0;
    }

    // The hi-lift radius scale above is carried into the coefficient too, so
    // that the ratio the cycle count actually depends on is unchanged and
    // these counts stay exactly where they were.
    const coefficient = this.hiLiftDrumData
        ? CYCLE_COEFFICIENT * HILIFT_RADIUS_SCALE
        : CYCLE_COEFFICIENT;

    const cycles = Math.pow(
        (coefficient * Math.pow(this.wireSizeNumber, CYCLE_WIRE_EXPONENT)) /
            torque,
        CYCLE_EXPONENT
    );

    return Math.round(cycles).toLocaleString("en-US");
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

    selectAssembly(event) {
        this.state.assembly = event.target.value;
    }

    selectSpringId(event) {
        this.state.springId = event.target.value;
    }

    selectCycles(event) {
        this.state.cycles = event.target.value;
    }

    selectDrum(event) {
        this.state.drum = event.target.value;
    }

    selectWeight(event) {
    this.state.weight = event.target.value;
    }   

    selectPitchAmount(event) {
        this.state.pitchAmount = event.target.value;
    }

    selectWireSize(event) {
        this.state.wireSize = event.target.value;
    }

    selectLiftIn(event) {
        this.state.liftin = event.target.value;
    }

    selectLiftType(event) {
        this.state.liftType = event.target.value;

    if (this.state.liftType === 'Hi-Lift') {
        this.state.radius = '15';
    }
}
}

registry
    .category("actions")
    .add("spring_engineering.calculator", SpringEngineering);