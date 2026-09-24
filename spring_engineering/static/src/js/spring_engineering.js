/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

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

get tippt() {
    return Math.round(
        (this.state.multiplier * Number(this.state.weight || 0)) * 100
    ) / 100;
}

get springIdCorrection() {
    const corrections = {
        
        '1 19/32"': -0.0126,
        '1 3/4"': -0.00732,
        '1 13/16"': -0.00542,
        '2"': 0,
        '2 3/16"': 0.00425,
        '2 1/4"': 0.00545,
        '2 7/16"': 0.00903,
        '2 1/2"': 0.01030,
        '2 5/8"': 0.0121,
        '2 3/4"': 0.01380,
        '2 25/32"': 0.01447,
        '3"': 0.01675,
        '3 1/8"': 0.018,
        '3 3/8"': 0.0208,
        '3 1/2"': 0.0216,
        '3 3/4"': 0.02385,
        '3 25/32"': 0.0239,
        '4"': 0.0255,
        '4 1/8"': 0.02633,
        '4 3/8"': 0.0275,
        '4 1/2"': 0.0285,
        '4 7/8"': 0.031,
        '5 1/8"': 0.0325,
        '5 1/4"': 0.033,
        '5 1/2"': 0.0335,
        '5 3/4"': 0.034,
        '5 7/8"': 0.0346,
        '6"': 0.035,
        '6 1/2"': 0.0358,
        '7 5/8"': 0.0385,
        '7 3/4"': 0.03866,
        '8 1/2"': 0.039,
        
    };

    return corrections[this.state.springId] ?? 0;
}

get wireSizeCorrection() {
    const corrections = {

        '0.125"':  -0.27461187,
        '0.135"':  -0.20552170,
        '0.142"':  -0.16355250,
        '0.1483"': -0.13372197,
        '0.1562"': -0.09964900,
        '0.162"':  -0.08003673,
        '0.17"':   -0.05821172,
        '0.177"':  -0.04359530,
        '0.1875"': -0.026,
        '0.192"':  -0.02115813,
        '0.2"':    -0.01388889,
        '0.207"':  -0.00870253,
        '0.2187"': -0.00368324,
        '0.2253"': -0.00160342, 
        '0.2343"': -0.00044504, 
        '0.2437"': 0,
        '0.25"': 0,
        '0.2625"': -0.00104,
        '0.273"': -0.00215,
        '0.283"': -0.00362,
        '0.289"': -0.00458,
        '0.295"': -0.00578,
        '0.3065"': -0.00788,
        '0.3125"': -0.009,
        '0.3195"': -0.0103,
        '0.331"': -0.013,
        '0.3437"': -0.0153,
        '0.3625"': -0.0192,
        '0.375"': -0.02175,
        '0.3938"': -0.02553,
        '0.4062"': -0.028,
        '0.4218"': -0.03105, 
        '0.4305"': -0.03273,
        '0.4375"': -0.03406,
        '0.4531"': -0.03702491,
        '0.4615"': -0.03858015,
        '0.4687"': -0.03992031,
        '0.49"': -0.04378670,
        '0.5"': -0.04557906,
        '0.5312"': -0.05103852,
        '0.5625"': -0.05634456,
        '0.625"': -0.06648102,

    };

    return corrections[this.state.wireSize] ?? 0;
}

get wireSizeNumber() {
    return Number(this.state.wireSize.replace('"', '').trim());
}

get meanDiameter() {
    return this.springIdNumber + (this.wireSizeNumber / 2);
}

get divider() {
    return (
        (30000000 * Math.pow(this.wireSizeNumber, 5)) /
        (10.8 * this.meanDiameter)
    );
}

get springLength() {
    if (!this.tippt) {
        return 0;
    }

    const endAddition = this.springIdNumber > 4.5 ? 0.75 : 1.25;

    const baseLength =
        (this.state.springs * this.divider) / this.tippt + endAddition;

    const correctedLength =
        baseLength *
        (1 + this.springIdCorrection) *
        (1 + this.wireSizeCorrection);

    return Math.round(correctedLength * 100) / 100;
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

    selectLiftType(event) {
        this.state.liftType = event.target.value;
    }

    selectDrum(event) {
    this.state.drum = event.target.value;
        //these numbers are at 7ft in height and need to change depending on the height
    if (this.state.drum === "AMBASSADOR D-101") {
    this.state.multiplier = 0.440974;
    this.state.turns = 6.17;
    } 
    else if (this.state.drum === "CANIMEX/TF D400-123") {
        this.state.multiplier = 0.290899;
        this.state.turns = 7.88;
    } 
    else if (this.state.drum === "CANIMEX/TF D400-144") {
        this.state.multiplier = 0.291033;
        this.state.turns = 7.88;
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