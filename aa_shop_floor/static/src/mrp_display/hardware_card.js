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

import { Component, onWillStart, useState } from "@odoo/owl";
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

    setup() {
        this.orm = useService("orm");
        // THE LABEL STOCK, BESIDE THE BUTTON THAT PRINTS ON IT (owner,
        // 2026-10-19). Loaded when the dialog opens rather than carried on
        // every card, because it is one answer for the whole shop and not
        // something about this box.
        this.sizes = useState({ current: "", options: [] });

        onWillStart(async () => {
            Object.assign(
                this.sizes,
                await this.orm.call("mrp.production", "aa_sticker_sizes", [])
            );
        });
    }

    get title() {
        const card = this.props.card;

        return [card.order, card.door].filter(Boolean).join(" · ") || "Hardware";
    }

    async onChangeSize(ev) {
        // Saved before anything is printed, so Print sticker prints on what
        // the dropdown says - and so the next box prints on it too, which is
        // the point of changing it here.
        Object.assign(
            this.sizes,
            await this.orm.call("mrp.production", "aa_set_sticker_size", [
                ev.target.value,
            ])
        );
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

    aaProductionId() {
        const record = this.props.record;

        return record.resModel === "mrp.production"
            ? record.resId
            : record.data.production_id.id;
    },

    aaOpenHardwareCard() {
        const card = this.aaHardwareCard();

        if (!card) {
            return;
        }

        this.aaDialog.add(AaHardwareCardDialog, {
            card,
            productionId: this.aaProductionId(),
        });
    },

    // THE PRINT BUTTON ON THE CARD (owner, 2026-10-28): the same PDF the
    // dialog's Print sticker opens, in a tab of its own so the tablet's print
    // dialog can reach the label printer.
    aaPrintSticker() {
        if (!this.aaHardwareCard()) {
            return;
        }
        window.open(
            `/report/pdf/aa_shop_floor.report_hardware_sticker/${this.aaProductionId()}`,
            "_blank"
        );
    },
});
