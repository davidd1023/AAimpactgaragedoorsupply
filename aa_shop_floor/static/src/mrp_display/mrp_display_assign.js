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

    async aaRelease(method) {
        const record = this.props.record;
        await this.model.orm.call("mrp.production", method, [[record.resId]]);
        await this.env.reload(record);
    },
});
