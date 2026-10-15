import { onWillUnmount, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

// Overview: the manager puts an order on its own station, or takes it back off.
patch(MrpDisplayRecord.prototype, {
    setup() {
        super.setup(...arguments);
        // The station timer on the Overview card counts up while the job runs.
        this.aaClock = useState({ now: Date.now() });
        const tick = setInterval(() => (this.aaClock.now = Date.now()), 15000);
        onWillUnmount(() => clearInterval(tick));
    },

    aaJobMinutes(job) {
        let minutes = job.minutes || 0;
        if (job.running_since) {
            minutes += Math.max(0, (this.aaClock.now - Date.parse(job.running_since)) / 60000);
        }
        return minutes;
    },

    aaJobTime(job) {
        const total = Math.floor(this.aaJobMinutes(job));
        const hours = Math.floor(total / 60);
        const minutes = total % 60;
        return hours ? `${hours} h ${String(minutes).padStart(2, "0")} min` : `${minutes} min`;
    },

    aaJobHasTime(job) {
        return Boolean(job.running_since || job.minutes);
    },

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
        return items ? `${title}: ${items} ${items === 1 ? "item" : "items"}` : title;
    },

    aaOrder() {
        try {
            return JSON.parse(this.props.record.data.aa_order_board || "{}");
        } catch {
            return {};
        }
    },

    aaJobBadge(job) {
        switch (job.status) {
            case "pending":
                return { cls: "text-bg-warning", text: "Pending" };
            case "progress":
                return { cls: "text-bg-primary", text: `In progress · ${job.station}` };
            case "done":
                return { cls: "text-bg-success", text: "Done" };
            case "none":
                return { cls: "text-bg-secondary", text: "No work orders" };
            default:
                return { cls: "text-bg-info", text: job.station };
        }
    },

    async aaOrderAction(method, productionIds) {
        await this.model.orm.call("mrp.production", method, [productionIds]);
        await this.env.reload();
    },

    async aaRelease(method) {
        const record = this.props.record;
        await this.model.orm.call("mrp.production", method, [[record.resId]]);
        await this.env.reload(record);
    },
});
