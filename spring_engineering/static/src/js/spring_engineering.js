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
// Below MIN_HI_LIFT the reference calculator freezes: 6", 8", 9", 10" and 11"
// all return bit-identical output, equal to HL = 0. At exactly 0 it hides the
// results rows instead (see `resultsVisible`).
const HILIFT_MIN = 12;

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
        return hiLiftREff(this.hiLiftDrumData, this.hiLiftInches);
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

        return multiplier > 0 ? this.rEffExact / multiplier : 0;
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
        return hiLiftMultiplier(
            this.hiLiftDrumData,
            this.doorHeightTotalFeet,
            this.hiLiftInches
        );
    }

    // Derived from turns via the constant drum radius, which is what keeps the
    // cycle count height-independent.
    if (!this.drumData || !this.turnsExact) {
        return 0;
    }

    return this.drumData.rEff / this.turnsExact;
}

get resultsVisible() {
    // The reference calculator reveals the results rows only once it has
    // everything it needs. A hi-lift drum with the hi-lift left at 0 (or
    // blank) is the case that matters here - it shows nothing at all, so
    // neither do we. Anything from 1" up computes, clamped to 0 below 12".
    //
    // The multiplier check covers the far corner of the surface: short door,
    // long hi-lift. The multiplier collapses through zero there, and past the
    // crossing turns would go negative, which the reference has never been
    // observed to display.
    if (this.hiLiftDrumData) {
        return this.hiLiftInches > 0 && this.multiplierExact > 0;
    }

    return true;
}

get multiplier() {
    // The reference calculator shows 6 decimals.
    return Math.round(this.multiplierExact * 1000000) / 1000000;
}

get tipptExact() {
    // Unrounded IPPT. `tippt` below is rounded to 2 dp for display and for the
    // spring-length formula (which matches the reference results exactly that
    // way). Cycle life must NOT use the rounded value: it varies as the 4.67th
    // power of torque, so a 0.01 rounding of IPPT moves the cycle count by
    // ~0.05% - enough to miss by 179 cycles at 150 lb.
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

    const cycles = Math.pow(
        (CYCLE_COEFFICIENT *
            Math.pow(this.wireSizeNumber, CYCLE_WIRE_EXPONENT)) /
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