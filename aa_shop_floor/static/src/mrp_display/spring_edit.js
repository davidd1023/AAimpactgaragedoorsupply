import { _t } from "@web/core/l10n/translation";
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { SpringEngineering } from "@spring_engineering/js/spring_engineering";

// CHANGE A SPRING BEFORE IT IS WOUND (owner, 2026-11-25): wire, I.D., drum,
// lift type and hi-lift, recalculated and re-priced.
//
// THE CALCULATOR RUNS HEADLESS, the way the Quick Order's spring_bridge.js
// runs it: the component computes everything from getters over `state`, so an
// instance with a plain state and no rendering gives the same wire, length and
// turns the Spring Calculator page shows. No second spring model.

const SPRING_IDS = ['2 5/8"', '3 3/4"', '5 1/4"'];
const STANDARD_DRUMS = ["CANIMEX/TF D400-96", "CANIMEX/TF D400-144", "CANIMEX/TF D525-216"];
const HILIFT_DRUMS = ["CANIMEX/TF 525-54HL", "CANIMEX/TF 575-120", "CANIMEX/TF D800-120"];
const CYCLES = ["10,000", "25,000", "50,000", "100,000"];

function headless(form, wire) {
    const calc = Object.create(SpringEngineering.prototype);
    calc.rates = null;
    const height = Number(form.heightIn) || 0;
    const width = Number(form.widthIn) || 0;
    const hiLift = form.liftType === "Hi-Lift";
    calc.state = {
        assembly: "Single",
        springs: Number(form.springs) || 2,
        springId: form.springId,
        cycles: form.cycles,
        cartBusy: false,
        cartError: "",
        liftType: hiLift ? "Hi-Lift" : "Standard",
        liftin: hiLift ? String(form.hiLift || "") : "",
        radius: hiLift ? "15" : String(form.radius || "15"),
        drum: form.drum,
        doorWidthFeet: Math.floor(width / 12),
        doorWidthInches: Math.round(width % 12),
        doorHeightFeet: Math.floor(height / 12),
        doorHeightInches: Math.round(height % 12),
        weight: form.weight ? String(form.weight) : "",
        pitch: false,
        pitchAmount: "0/12",
        wireSize: wire ? String(wire) + '"' : '0.25"',
        showWarnings: false,
        showDrumInfo: false,
    };
    return calc;
}

export class AaSpringEditDialog extends Component {
    static template = "aa_shop_floor.SpringEditDialog";
    static components = { Dialog };
    static props = ["item", "order", "onSaved", "close"];

    setup() {
        this.orm = useService("orm");
        const start = this.props.item.start;
        const hiLiftDrum = HILIFT_DRUMS.includes(start.drum);
        this.form = useState({
            springs: start.springs,
            springId: SPRING_IDS.includes(start.spring_id) ? start.spring_id : SPRING_IDS[0],
            wire: "auto",
            drum: start.drum || STANDARD_DRUMS[0],
            liftType: hiLiftDrum || start.hi_lift ? "Hi-Lift" : "Standard",
            hiLift: start.hi_lift || "",
            radius: "15",
            cycles: CYCLES.includes(start.cycles) ? start.cycles : "10,000",
            weight: start.weight,
            heightIn: start.height_in,
            widthIn: start.width_in,
        });
        this.ui = useState({ price: null, busy: false, error: "" });
        this.springIds = SPRING_IDS;
        this.cyclesList = CYCLES;
        this.stocked = headless(this.form, null).stockedWireLabels.map((w) => parseFloat(w));
        onWillStart(() => this.reprice());
    }

    get drums() {
        return this.form.liftType === "Hi-Lift" ? HILIFT_DRUMS : STANDARD_DRUMS;
    }

    get start() {
        return this.props.item.start;
    }

    // Everything on screen comes from here, so the figures always match the form.
    get result() {
        const calc = headless(this.form, null);
        if (!calc.state.drum || !this.drums.includes(calc.state.drum)) {
            return { error: _t("Choose a drum for this lift type.") };
        }
        if (!calc.resultsVisible) {
            return { error: _t("Enter the door weight and height.") };
        }
        const recommended = calc.recommendedWire;
        const wire = this.form.wire === "auto" ? recommended : Number(this.form.wire);
        const sized = headless(this.form, wire);
        const warnings = (sized.warnings || []).map((w) => ({ severity: w.severity, message: w.message }));
        return {
            recommended,
            wire,
            length: sized.springLength,
            turns: sized.turns,
            warnings,
            red: warnings.some((w) => w.severity === "red"),
            spec: sized.cartSpec,
        };
    }

    async onChange() {
        // t-model writes the value on the same event; let it land first.
        await Promise.resolve();
        await this.reprice();
    }

    async reprice() {
        const result = this.result;
        if (result.error) {
            this.ui.price = null;
            return;
        }
        try {
            this.ui.price = await this.orm.call("sale.order.line", "aa_quote_spring",
                [[this.props.item.line_id], result.spec]);
            this.ui.error = "";
        } catch (error) {
            this.ui.price = null;
            this.ui.error = error.data?.message || error.message || String(error);
        }
    }

    setLift(type) {
        this.form.liftType = type;
        if (!this.drums.includes(this.form.drum)) {
            this.form.drum = this.drums[0];
        }
        this.onChange();
    }

    async save() {
        const result = this.result;
        if (result.error || result.red || this.ui.busy) {
            return;
        }
        this.ui.busy = true;
        try {
            const saved = await this.orm.call("sale.order.line", "aa_respec_spring",
                [[this.props.item.line_id], result.spec]);
            this.props.close();
            await this.props.onSaved(saved);
        } catch (error) {
            this.ui.error = error.data?.message || error.message || String(error);
        } finally {
            this.ui.busy = false;
        }
    }

    fmtWire(wire) {
        return wire ? String(wire).replace(/^0/, "") + '"' : "-";
    }
}
