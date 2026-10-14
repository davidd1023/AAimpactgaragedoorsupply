import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

// Overview: the manager sends each work order of the card to a station.
patch(MrpDisplayRecord.prototype, {
    aaBoard() {
        try {
            return JSON.parse(this.props.record.data.aa_station_board || "{}");
        } catch {
            return {};
        }
    },

    async aaAssign(workorderId, workcenterId) {
        await this.model.orm.call("mrp.workorder", "aa_assign_workcenter", [[workorderId], workcenterId]);
        await this.env.reload(this.props.record);
    },
});
