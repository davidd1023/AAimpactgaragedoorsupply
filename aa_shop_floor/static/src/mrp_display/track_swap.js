/** @odoo-module **/
// CUT IT FROM A LONGER TRACK (owner, 2026-11-11).
//
// A button on the Track Prep card. When the RAW track a job asks for is not on
// the rack, Jorge picks a longer one of the same size, kind and colour that
// is in stock, and that is what comes off inventory when the job is done. The
// offcut is thrown away, for now. A merged card carries several jobs (the
// vertical and the horizontal), so the dialog lists each of them.

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

export class AaTrackSwapDialog extends Component {
    static template = "aa_shop_floor.TrackSwapDialog";
    static components = { Dialog };
    static props = {
        productionIds: Array,
        onDone: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // ONE PICK PER JOB, keyed by production: a merged card carries the
        // horizontal and the vertical, and both may need a longer piece.
        this.state = useState({ board: [], busy: false, picked: {} });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.board = await this.orm.call(
            "mrp.production", "aa_track_swap_board", [this.props.productionIds]);
    }

    // A tap picks, a second tap on the same piece unpicks; nothing changes
    // until the button at the bottom. It takes real pieces off the count, and
    // a tablet gets brushed.
    pick(job, option) {
        const picked = this.state.picked;
        if (picked[job.production_id] && picked[job.production_id].id === option.id) {
            delete picked[job.production_id];
        } else {
            picked[job.production_id] = option;
        }
    }

    isPicked(job, option) {
        const chosen = this.state.picked[job.production_id];
        return Boolean(chosen) && chosen.id === option.id;
    }

    isShort(job, option) {
        return option.on_hand < job.needs;
    }

    get pickedCount() {
        return Object.keys(this.state.picked).length;
    }

    async confirm() {
        const entries = Object.entries(this.state.picked);
        if (!entries.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        const done = [];
        try {
            for (const [productionId, option] of entries) {
                const result = await this.orm.call(
                    "mrp.production", "aa_track_swap", [[Number(productionId)], option.id]);
                done.push(result.track);
            }
        } finally {
            this.state.busy = false;
            if (done.length) {
                this.notification.add(`Cut from ${done.join(", ")}`, { type: "success" });
                await this.props.onDone();
            }
        }
        this.props.close();
    }
}

patch(MrpDisplayRecord.prototype, {
    aaTrackSwappable() {
        const data = this.props.record.data;
        return Boolean(data.aa_track_swappable) && !["done", "cancel"].includes(data.state);
    },

    aaOpenTrackSwap() {
        const ids = [this.aaProductionId()];
        // The jobs drawn on this card too, when it carries an order's others.
        try {
            const merge = JSON.parse(this.props.record.data.aa_track_merge || "null");
            for (const partner of (merge && merge.partners) || []) {
                if (!ids.includes(partner.production_id)) {
                    ids.push(partner.production_id);
                }
            }
        } catch {
            // No merge data: just this job.
        }
        const record = this.props.record;
        this.aaDialog.add(AaTrackSwapDialog, {
            productionIds: ids,
            onDone: () => this.env.reload(record),
        });
    },
});
