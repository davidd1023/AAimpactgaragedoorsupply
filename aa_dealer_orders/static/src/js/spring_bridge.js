/** @odoo-module **/
// Lets the dealer Quick Order page use the Spring Engineering calculator WITHOUT a
// second copy of its spring model. The calculator component computes everything
// from getters over `this.state`, so a headless instance (the prototype, a plain
// state object, no rendering) gives the same wire / length / cycles the
// /spring-calculator page shows for the same door.
import { SpringEngineering } from "@spring_engineering/js/spring_engineering";

// Quick Order drum -> the calculator's drum names.
const DRUM_NAMES = {
    "D400-96": "CANIMEX/TF D400-96",
    "D400-144": "CANIMEX/TF D400-144",
    "D525-216": "CANIMEX/TF D525-216",
    "D525-54": "CANIMEX/TF 525-54HL",
    "D575-120": "CANIMEX/TF 575-120",
    "D800-120": "CANIMEX/TF D800-120",
};

window.aaSpringCalc = function (door) {
    const duplex = door.springId.includes("inside");
    const calc = Object.create(SpringEngineering.prototype);
    calc.rates = null;
    calc.state = {
        assembly: duplex ? "Duplex" : "Single",
        springs: Number(door.springs) || 2,
        springId: door.springId,
        cycles: door.cycles || "10,000",
        cartBusy: false,
        cartError: "",
        liftType: door.liftType === "highlift" ? "Hi-Lift" : "Standard",
        liftin: door.liftType === "highlift" ? String(door.highLift || "") : "",
        radius: door.liftType === "highlift" ? "15" : (String(door.trackType || "").endsWith("12R") ? "12" : "15"),
        drum: DRUM_NAMES[door.drum] || "",
        doorWidthFeet: Math.floor((door.widthIn || 0) / 12),
        doorWidthInches: Math.round((door.widthIn || 0) % 12),
        doorHeightFeet: Math.floor((door.heightIn || 0) / 12),
        doorHeightInches: Math.round((door.heightIn || 0) % 12),
        weight: door.weight ? String(door.weight) : "",
        pitch: false,
        pitchAmount: "0/12",
        wireSize: '0.25"',
        showWarnings: false,
        showDrumInfo: false,
    };
    if (!calc.state.drum) {
        return { error: "No spring model for this drum." };
    }
    if (!calc.resultsVisible) {
        return { error: "Enter the door weight and height for springs." };
    }
    const wire = calc.recommendedWire;
    if (wire !== null) {
        calc.state.wireSize = String(wire) + '"';
    }
    const spec = calc.cartSpec;
    return {
        spec,
        warnings: (calc.warnings || []).map((w) => ({ severity: w.severity, message: w.message })),
    };
};
