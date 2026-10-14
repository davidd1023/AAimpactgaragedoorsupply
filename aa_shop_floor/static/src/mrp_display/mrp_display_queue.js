import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

// First in, first out (owner, 2026-10-14): orders show in the order they came
// in, so everyone knows what is next. Starred (priority) orders still go first;
// at a station, work already started stays on top.
const WO_STATE_RANK = { progress: 0, ready: 1, pending: 2, waiting: 3, blocked: 3, done: 4 };

patch(MrpDisplay.prototype, {
    defineRelevantRecords() {
        const records = super.defineRelevantRecords(...arguments) || [];
        const showMOs = this.state.activeResModel === "mrp.production";
        const moId = (rec) => (showMOs ? rec.resId : rec.data.production_id?.id || 0);
        const sorted = [...records].sort((a, b) => {
            const pa = Number(a.data.priority || 0);
            const pb = Number(b.data.priority || 0);
            if (pa !== pb) {
                return pb - pa;
            }
            if (!showMOs) {
                const sa = WO_STATE_RANK[a.data.state] ?? 3;
                const sb = WO_STATE_RANK[b.data.state] ?? 3;
                if (sa !== sb) {
                    return sa - sb;
                }
            }
            return moId(a) - moId(b) || a.resId - b.resId;
        });
        this._relevantRecords = sorted;
        return sorted;
    },
});
