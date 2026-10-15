import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

// First in, first out (owner, 2026-10-14): orders show in the order they came
// in, so everyone knows what is next. Starred (priority) orders still go first;
// at a station, work already started stays on top.
const WO_STATE_RANK = { progress: 0, ready: 1, pending: 2, waiting: 3, blocked: 3, done: 4 };

patch(MrpDisplay.prototype, {
    defineRelevantRecords() {
        const showMOs = this.state.activeResModel === "mrp.production";
        let records = super.defineRelevantRecords(...arguments) || [];
        if (showMOs) {
            // One card per sale order: the order's first MO that passes the
            // current filters carries the card (a filter such as "MO Ready" may
            // hide the track orders, so it can't always be the first MO).
            const orderOf = (rec) => {
                try {
                    const board = JSON.parse(rec.data.aa_order_board || "{}");
                    return board.grouped ? board.order : false;
                } catch {
                    return false;
                }
            };
            const carrier = {};
            for (const rec of records) {
                const order = orderOf(rec);
                if (order && (!(order in carrier) || rec.resId < carrier[order])) {
                    carrier[order] = rec.resId;
                }
            }
            records = records.filter((rec) => {
                const order = orderOf(rec);
                return !order || carrier[order] === rec.resId;
            });
        }
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
