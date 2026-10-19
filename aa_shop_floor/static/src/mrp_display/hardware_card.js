/** @odoo-module **/
// WHAT THE BOX IS FOR, on the Hardware card.
//
// A button beside Start (owner, 2026-10-19). It opens the door's figures - the
// spring and its turns, the drum they were worked out on, the finish, the lift,
// the cable and the track - and prints the sticker that goes in the box.
//
// THE BUTTON IS NOT THERE WHEN THERE IS NOTHING TO SHOW. aa_hardware_card is
// empty for every job that is not a hardware kit, and for a kit whose order
// says none of those things, so "don't display anything" needs no condition of
// its own here: the card either has rows or does not exist.

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

export class AaHardwareCardDialog extends Component {
    static template = "aa_shop_floor.HardwareCardDialog";
    static components = { Dialog };
    static props = {
        card: Object,
        productionId: Number,
        close: Function,
    };

    get title() {
        const card = this.props.card;

        return [card.order, card.door].filter(Boolean).join(" · ") || "Hardware";
    }

    // THE PDF, IN A TAB OF ITS OWN, which is what a tablet can actually print
    // from: the browser's own print dialog knows about the label printer and
    // nothing in here does.
    printSticker() {
        window.open(
            `/report/pdf/aa_shop_floor.report_hardware_sticker/${this.props.productionId}`,
            "_blank"
        );
    }
}

patch(MrpDisplayRecord.prototype, {
    setup() {
        super.setup();
        this.aaDialog = useService("dialog");
    },

    aaHardwareCard() {
        try {
            return JSON.parse(this.props.record.data.aa_hardware_card || "null");
        } catch {
            return null;
        }
    },

    aaOpenHardwareCard() {
        const card = this.aaHardwareCard();

        if (!card) {
            return;
        }

        const record = this.props.record;
        const productionId =
            record.resModel === "mrp.production"
                ? record.resId
                : record.data.production_id.id;

        this.aaDialog.add(AaHardwareCardDialog, { card, productionId });
    },
});
