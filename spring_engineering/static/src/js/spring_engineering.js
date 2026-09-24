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