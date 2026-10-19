/** @odoo-module **/
// WHAT HAS BEEN MADE, inside the Shop Floor.
//
// The owner, 2026-10-19: a history option in the Shop Floor showing all the
// finished parts of an order - hardware, springs, tracks - and how long each
// took after it was started.
//
// TWO DOORS TO ONE LIST. The Shop Floor's own menu opens the last few orders
// ("what have we been making"); the History button on an order card opens that
// order ("what is left on this one, and how long did the rest take"). Both show
// the same rows from the same server call, which reads Odoo's own work order
// clock - the figures the Shop Floor History list in Reporting has always
// shown. Nothing is recorded twice.

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

export class AaShopFloorHistoryDialog extends Component {
    static template = "aa_shop_floor.HistoryDialog";
    static components = { Dialog };
    static props = {
        order: { type: [String, Boolean], optional: true },
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ loading: true, groups: [] });

        onWillStart(async () => {
            this.state.groups = await this.orm.call(
                "mrp.workorder",
                "aa_shop_floor_history",
                [],
                { order: this.props.order || false }
            );
            this.state.loading = false;
        });
    }

    get title() {
        return this.props.order
            ? `History · ${this.props.order}`
            : "Shop Floor History";
    }
}

// The Shop Floor's own options menu, where Reload Data already lives.
patch(MrpDisplay.prototype, {
    setup() {
        super.setup();
        this.aaHistoryDialog = useService("dialog");
    },

    aaOpenHistory(order) {
        this.aaHistoryDialog.add(AaShopFloorHistoryDialog, { order: order || false });
    },
});

// And one order's own history, from its card in the Overview. Its own service
// reference rather than the one the hardware card's patch happens to set, so
// neither file depends on the other being loaded first.
patch(MrpDisplayRecord.prototype, {
    setup() {
        super.setup();
        this.aaHistoryDialog = useService("dialog");
    },

    aaOpenHistory(order) {
        this.aaHistoryDialog.add(AaShopFloorHistoryDialog, { order: order || false });
    },
});
