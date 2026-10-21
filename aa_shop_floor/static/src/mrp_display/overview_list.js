import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

// THE OVERVIEW AS A LIST (owner, 2026-10-21: "more than 60 orders" on the
// Shop Floor). The cards stay - one button switches between them - but with
// sixty orders a card per order is a page of scrolling per handful of orders.
// The list is one row per order: its W/O #, when it came in, who for, one
// coloured chip per station and how old it is. A click opens the row to show
// what each station makes, with the same Send / Remove / Mark as Done buttons
// the cards have.
//
// Everything here reads the same order board the cards read
// (aa_order_board), and every button calls the same server methods, so the
// two views can never disagree about an order.

const VIEW_KEY = "aa_shop_floor.overview_view";
// The stations in the order the shop thinks of them; any other station is
// listed after these.
const STATION_ORDER = ["Track Prep", "Hardware", "Springs"];

const CHIPS = {
    pending: { cls: "text-bg-warning", text: "Pending" },
    station: { cls: "text-bg-info", text: "Assigned" },
    progress: { cls: "text-bg-primary", text: "In progress" },
    done: { cls: "text-bg-success", text: "Done" },
    none: { cls: "text-bg-secondary", text: "No work orders" },
};

function readView() {
    try {
        return window.localStorage.getItem(VIEW_KEY) || "list";
    } catch {
        return "list";
    }
}

function parse(text) {
    try {
        return JSON.parse(text || "{}");
    } catch {
        return {};
    }
}

patch(MrpDisplay.prototype, {
    setup() {
        super.setup(...arguments);
        this.aaOverview = useState({
            view: readView(),
            tab: "all",
            station: "",
            query: "",
            open: {},
        });
    },

    // --- which view ------------------------------------------------------

    aaIsOverview() {
        return this.state.activeResModel === "mrp.production" && !this.state.firstLoad;
    },

    aaListActive() {
        return this.aaIsOverview() && this.aaOverview.view === "list";
    },

    aaSetView(view) {
        this.aaOverview.view = view;
        try {
            window.localStorage.setItem(VIEW_KEY, view);
        } catch {
            // A tablet that keeps nothing simply opens on the list each time.
        }
    },

    // --- the rows --------------------------------------------------------

    aaRowOf(record) {
        const board = parse(record.data.aa_order_board);
        let jobs = board.jobs || [];
        let order = board.order;
        let received = board.received;
        let canAssign = board.can_assign;
        let sendIds = board.send_ids || [];
        let removeIds = board.remove_ids || [];

        if (!jobs.length) {
            // A manufacturing order with no sale order behind it (made by
            // hand): the station board still says where it is.
            const station = parse(record.data.aa_station_board);
            const state = record.data.state;
            let status = "station";
            if (state === "done") {
                status = "done";
            } else if (state === "progress") {
                status = "progress";
            } else if (station.can_send) {
                status = "pending";
            }
            const id = record.resId;
            sendIds = station.can_send ? [id] : [];
            removeIds = station.can_remove ? [id] : [];
            jobs = [{
                id,
                station: station.station || "Other",
                status,
                items: [{ id, product: record.data.product_id?.display_name || "", summary: [], more: "" }],
                send_ids: sendIds,
                remove_ids: removeIds,
                done_ids: ["done", "cancel"].includes(state) ? [] : [id],
            }];
            order = record.data.aa_wo_number || record.data.name;
            received = station.received;
            canAssign = station.can_assign;
        }

        const byStation = {};
        for (const job of jobs) {
            byStation[job.station] = job;
        }
        const statuses = jobs.map((job) => job.status).filter((s) => s !== "none");
        let status = "station";
        if (statuses.length && statuses.every((s) => s === "done")) {
            status = "done";
        } else if (statuses.includes("pending")) {
            status = "pending";
        } else if (statuses.includes("progress")) {
            status = "progress";
        }
        const ageHours = board.received_utc
            ? Math.max(0, (Date.now() - Date.parse(board.received_utc)) / 3600000)
            : null;

        return {
            // BY THE ORDER, not the record: the records are new after every
            // reload, and a row the manager opened must stay open after he
            // presses Send.
            key: order || record.id,
            order: order || "",
            customer: board.customer || "",
            received: received || "",
            ageHours,
            canAssign: Boolean(canAssign),
            sendIds,
            removeIds,
            jobs,
            byStation,
            status,
        };
    },

    aaAllRows() {
        // relevantRecords is already one record per order, in the order the
        // orders came in (mrp_display_queue.js).
        return this.relevantRecords.map((record) => this.aaRowOf(record));
    },

    aaStations(rows) {
        const names = new Set();
        for (const row of rows) {
            for (const job of row.jobs) {
                names.add(job.station);
            }
        }
        const rank = (name) => {
            const index = STATION_ORDER.indexOf(name);
            return index < 0 ? STATION_ORDER.length : index;
        };
        return [...names].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
    },

    aaTabs(rows) {
        const count = (test) => rows.filter(test).length;
        return [
            { key: "all", label: "All", count: rows.length },
            { key: "assign", label: "To assign", count: count((r) => this.aaInTab(r, "assign")) },
            { key: "stations", label: "At stations", count: count((r) => this.aaInTab(r, "stations")) },
            { key: "progress", label: "In progress", count: count((r) => this.aaInTab(r, "progress")) },
        ];
    },

    aaInTab(row, tab) {
        const has = (status) => row.jobs.some((job) => job.status === status);
        switch (tab) {
            case "assign":
                return has("pending");
            case "stations":
                return has("station") || has("progress");
            case "progress":
                return has("progress");
            default:
                return true;
        }
    },

    aaFilterRows(rows) {
        const query = this.aaOverview.query.trim().toLowerCase();
        const station = this.aaOverview.station;
        return rows.filter((row) => {
            if (!this.aaInTab(row, this.aaOverview.tab)) {
                return false;
            }
            if (station && !row.byStation[station]) {
                return false;
            }
            if (query) {
                const text = `${row.order} ${row.customer}`.toLowerCase();
                // "209" finds "W/O #209" as well as "#209".
                return text.includes(query) || text.includes(query.replace(/^#/, ""));
            }
            return true;
        });
    },

    // --- how a row looks ---------------------------------------------------

    aaChip(status) {
        return CHIPS[status] || CHIPS.station;
    },

    aaAgeLabel(hours) {
        if (hours < 1) {
            return "New";
        }
        if (hours < 24) {
            return `${Math.floor(hours)} h`;
        }
        const days = Math.floor(hours / 24);
        return `${days} ${days === 1 ? "day" : "days"}`;
    },

    // Green under a day, yellow up to two, red after that.
    aaAgeClass(hours) {
        if (hours < 24) {
            return "text-bg-success";
        }
        if (hours < 48) {
            return "text-bg-warning";
        }
        return "text-bg-danger";
    },

    aaSetTab(tab) {
        this.aaOverview.tab = tab;
    },

    aaSetStation(station) {
        this.aaOverview.station = station;
    },

    aaSetQuery(query) {
        this.aaOverview.query = query;
    },

    aaToggleRow(key) {
        this.aaOverview.open[key] = !this.aaOverview.open[key];
    },

    // --- the buttons -------------------------------------------------------

    async aaListAction(method, ids) {
        if (!ids || !ids.length) {
            return;
        }
        await this.model.orm.call("mrp.production", method, [ids]);
        // The same reload the Reload Data menu does.
        await this.onClickRefresh();
    },
});
