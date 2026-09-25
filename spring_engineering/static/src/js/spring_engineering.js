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

export class SpringEngineering extends Component {

    static template = "spring_engineering.Calculator";

    setup() {
        this.state = useState({
            assembly: "Single",
            springs: 2,
            springId: '1 19/32"',
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

get turnsExact() {
    // Full-precision turns at the current door height. Everything computes
    // from this; `turns` below is only what the Turns row shows.
    if (!this.drumData) {
        return 0;
    }

    return drumTurns(this.drumData, this.doorHeightTotalFeet);
}

get turns() {
    return Math.round(this.turnsExact * 100) / 100;
}

get multiplierExact() {
    // Derived from turns via the constant drum radius, which is what keeps the
    // cycle count height-independent.
    if (!this.drumData || !this.turnsExact) {
        return 0;
    }

    return this.drumData.rEff / this.turnsExact;
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
    if (!this.tippt) {
        return 0;
    }

    const endCoils =
        this.springIdNumber > LARGE_ID_THRESHOLD
            ? END_COILS_LARGE_ID
            : END_COILS_SMALL_ID;

    const endAddition = endCoils * this.wireSizeNumber;

    return (this.state.springs * this.divider) / this.tippt + endAddition;
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