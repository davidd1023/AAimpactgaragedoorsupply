import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

// Overview: the manager puts an order on its own station, or takes it back off.
patch(MrpDisplayRecord.prototype, {
    aaBoard() {
        try {
            return JSON.parse(this.props.record.data.aa_station_board || "{}");
        } catch {
            return {};
        }
    },

    // Overview (manufacturing order cards): only the rows before the first
    // section - "Kit AA-1600", track cut, spring specs. The box contents stay
    // at the station (owner, 2026-10-14: too much detail in the Overview).
    aaSpecLimit(rows) {
        if (this.props.record.resModel !== "mrp.production") {
            return rows.length;
        }
        const index = rows.findIndex((row) => !row.split("|")[1]);
        return index < 0 ? rows.length : index;
    },

    aaSpecSummary(rows, limit) {
        const title = rows[limit].split("|")[0];
        const items = rows.slice(limit).filter((row) => row.split("|")[2] === "c").length;
        return items ? `${title}: ${items} items` : title;
    },

    async aaRelease(method) {
        const record = this.props.record;
        await this.model.orm.call("mrp.production", method, [[record.resId]]);
        await this.env.reload(record);
    },
});
