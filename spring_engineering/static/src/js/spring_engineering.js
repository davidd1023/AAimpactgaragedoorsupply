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

            //stuff
            multiplier: 0,
            turns: 0,

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

get tipptExact() {
    // Unrounded IPPT. `tippt` below is rounded to 2 dp for display and for the
    // spring-length formula (which matches the reference results exactly that
    // way). Cycle life must NOT use the rounded value: it varies as the 4.67th
    // power of torque, so a 0.01 rounding of IPPT moves the cycle count by
    // ~0.05% - enough to miss by 179 cycles at 150 lb.
    return this.state.multiplier * Number(this.state.weight || 0);
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
    if (!this.state.springs || !this.state.turns) {
        return 0;
    }

    return (this.tipptExact / this.state.springs) * this.state.turns;
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

get springLength() {
    if (!this.tippt) {
        return 0;
    }

    const endCoils =
        this.springIdNumber > LARGE_ID_THRESHOLD
            ? END_COILS_LARGE_ID
            : END_COILS_SMALL_ID;

    const endAddition = endCoils * this.wireSizeNumber;

    const baseLength =
        (this.state.springs * this.divider) / this.tippt + endAddition;

    return Math.round(baseLength * 100) / 100;
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
        //these numbers are at 7ft in height and need to change depending on the height
    if (this.state.drum === "CANIMEX/TF D400-144") {
        this.state.multiplier = 0.291033;
        this.state.turns = 7.88;
    }
    else if (this.state.drum === "CANIMEX/TF D400-96") {
        this.state.multiplier = 0.286584;
        this.state.turns = 7.94;
    } 
    else if (this.state.drum === "CANIMEX/TF D525-216") {
        this.state.multiplier = 0.485098;
        this.state.turns = 6.05;
    } 
    else {
        this.state.multiplier = 0;
        this.state.turns = 0;
    }
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