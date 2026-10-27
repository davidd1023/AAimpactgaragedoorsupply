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
        // BY DAY (owner, 2026-10-21: "not choose - organised by day"): from
        // the menu the History opens on the days, newest first, each day
        // with the orders whose parts were finished on it. One order's own
        // history (from its card) is already one order and stays as it was.
        this.state = useState({
            loading: true,
            groups: [],
            mode: this.props.order ? "recent" : "day",
            days: [],
            more: false,
            dayLimit: 7,
            // TIMES (owner, 2026-10-27): "average time per task type, per
            // worker, per day", asked for here rather than in the back
            // office because a tablet bolted to a bench cannot reach a
            // Reporting menu.
            timesAllowed: false,
            times: [],
            timeDays: 30,
            timeGroup: "worker_task",
        });

        onWillStart(async () => {
            // Whether to show the tab at all. The server refuses as well -
            // hiding a button is not a lock.
            this.state.timesAllowed = await this.orm.call(
                "mrp.workorder", "aa_station_times_allowed", []
            );

            if (this.state.mode === "day") {
                await this.loadDays();
            } else {
                await this.loadRecent();
            }
        });
    }

    async loadRecent() {
        this.state.loading = true;
        this.state.groups = await this.orm.call(
            "mrp.workorder",
            "aa_shop_floor_history",
            [],
            { order: this.props.order || false }
        );
        this.state.loading = false;
    }

    async loadDays() {
        this.state.loading = true;
        const result = await this.orm.call(
            "mrp.workorder",
            "aa_shop_floor_history_by_day",
            [],
            { days: this.state.dayLimit }
        );
        this.state.days = result.days;
        this.state.more = result.more;
        this.state.loading = false;
    }

    async loadTimes() {
        this.state.loading = true;
        const result = await this.orm.call(
            "mrp.workorder",
            "aa_station_times",
            [],
            { days: this.state.timeDays, group: this.state.timeGroup }
        );
        this.state.times = result.rows || [];
        this.state.loading = false;
    }

    async setTimePeriod(days) {
        this.state.timeDays = days;
        await this.loadTimes();
    }

    async setTimeGroup(group) {
        this.state.timeGroup = group;
        await this.loadTimes();
    }

    async setMode(mode) {
        this.state.mode = mode;
        if (mode === "day") {
            await this.loadDays();
        } else if (mode === "times") {
            await this.loadTimes();
        } else {
            await this.loadRecent();
        }
    }

    async showOlderDays() {
        this.state.dayLimit += 7;
        await this.loadDays();
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
