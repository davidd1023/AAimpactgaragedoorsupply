import { _t } from "@web/core/l10n/translation";
import { useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
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

// SORT BY W/O (owner, 2026-11-02: "que pueda organizar de mayor a menor en
// los # de w/o de nosotros y de AA impact"). Clicking W/O # or AA Impact W/O
// sorts highest first, a second click lowest first, a third goes back to the
// order the orders came in - which stays the default, because that is the
// order the shop works them in.
const SORT_KEY = "aa_shop_floor.overview_sort";
const SORT_COLUMNS = { order: "order", aa_impact: "aaImpactWo" };

function readSort() {
    try {
        const saved = JSON.parse(window.localStorage.getItem(SORT_KEY) || "null");
        if (saved && SORT_COLUMNS[saved.column] && ["desc", "asc"].includes(saved.dir)) {
            return saved;
        }
    } catch {
        // Nothing kept: arrival order.
    }
    return { column: "", dir: "" };
}

// "W/O #269" -> 269, "1026" -> 1026. A PO that is not a number, or no W/O at
// all, gives null and sorts after every numbered order either way.
function woNumber(text) {
    const match = String(text || "").match(/\d+/);
    return match ? parseInt(match[0], 10) : null;
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
            sort: readSort(),
        });
        this.aaPartsDialog = useService("dialog");
        this.aaPartsNotify = useService("notification");
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
            aaImpactWo: board.aa_impact_wo || "",
            received: received || "",
            ageHours,
            canAssign: Boolean(canAssign),
            sendIds,
            removeIds,
            jobs,
            byStation,
            status,
            parts: board.parts || null,
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
        const kept = rows.filter((row) => {
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
        return this.aaSortRows(kept);
    },

    // --- sorting by W/O ------------------------------------------------------

    aaSortRows(rows) {
        const { column, dir } = this.aaOverview.sort;
        const field = SORT_COLUMNS[column];
        if (!field || !dir) {
            return rows; // arrival order
        }
        const sign = dir === "desc" ? -1 : 1;
        // Array.sort is stable, so equal numbers keep their arrival order.
        return [...rows].sort((a, b) => {
            const x = woNumber(a[field]);
            const y = woNumber(b[field]);
            if (x === null || y === null) {
                return x === y ? 0 : x === null ? 1 : -1;
            }
            return sign * (x - y);
        });
    },

    // desc -> asc -> arrival order -> desc ...
    aaToggleSort(column) {
        const sort = this.aaOverview.sort;
        if (sort.column !== column) {
            this.aaOverview.sort = { column, dir: "desc" };
        } else if (sort.dir === "desc") {
            this.aaOverview.sort = { column, dir: "asc" };
        } else {
            this.aaOverview.sort = { column: "", dir: "" };
        }
        try {
            window.localStorage.setItem(SORT_KEY, JSON.stringify(this.aaOverview.sort));
        } catch {
            // A tablet that keeps nothing opens in arrival order.
        }
    },

    aaSortIcon(column) {
        const sort = this.aaOverview.sort;
        if (sort.column !== column) {
            return "fa-sort text-muted";
        }
        return sort.dir === "desc" ? "fa-sort-numeric-desc" : "fa-sort-numeric-asc";
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

    // THE CARD'S OWN WORDS IN THE USER'S LANGUAGE (owner, 2026-11-11). The
    // rows are stored in English ("Cut to|160\" (LH + RH)"), so the label -
    // and a value that is a fixed phrase - is looked up in i18n/es.po here;
    // anything not listed there (a size, a count) comes back unchanged.
    aaT(text) {
        return text ? String(_t(text)) : text;
    },

    aaToggleRow(key) {
        this.aaOverview.open[key] = !this.aaOverview.open[key];
    },

    // --- the buttons -------------------------------------------------------

    // ADD / REMOVE A BOX, TRACKS OR SPRINGS (owner, 2026-11-02, admins only).
    // Add opens the Quick Order page filled with the order's doors - the spring
    // calculator runs there and nowhere else - and comes back here afterwards.
    aaAddPart(parts, part) {
        window.location.href = `/dealer/order/add/${parts.order_id}?part=${part}&back=shop-floor`;
    },

    aaRemovePart(parts, item, order) {
        this.aaPartsDialog.add(ConfirmationDialog, {
            title: _t("Remove %s", _t(item.label)),
            body: _t("Take the %(part)s off %(order)s? Their Shop Floor work is cancelled, " +
                "the lines go to 0 and the unpaid invoice is redone.",
                { part: String(_t(item.label)).toLowerCase(), order }),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                try {
                    const message = await this.model.orm.call("sale.order", "aa_remove_part", [[parts.order_id], item.part]);
                    this.aaPartsNotify.add(message, { type: "success" });
                } catch (error) {
                    this.aaPartsNotify.add(error.data?.message || error.message || String(error), { type: "danger" });
                }
                await this.onClickRefresh();
            },
            cancel: () => {},
        });
    },

    // SEND BACK (owner, 2026-11-11, admins): a job marked done by mistake goes
    // back to its station, and the stock it moved is put back.
    aaSendBack(job, order) {
        this.aaPartsDialog.add(ConfirmationDialog, {
            title: _t("Send back %s", job.station),
            body: _t("%(station)s on %(order)s was marked done. Send it back to the station as not done? " +
                "The stock it moved is put back and the station gets the job again.",
                { station: job.station, order }),
            confirmLabel: _t("Send back"),
            confirm: async () => {
                try {
                    await this.model.orm.call("mrp.production", "aa_send_back", [job.send_back_ids]);
                    this.aaPartsNotify.add(_t("%(station)s on %(order)s is back at the station.", { station: job.station, order }), { type: "success" });
                } catch (error) {
                    this.aaPartsNotify.add(error.data?.message || error.message || String(error), { type: "danger" });
                }
                await this.onClickRefresh();
            },
            cancel: () => {},
        });
    },

    async aaListAction(method, ids) {
        if (!ids || !ids.length) {
            return;
        }
        await this.model.orm.call("mrp.production", method, [ids]);
        // The same reload the Reload Data menu does.
        await this.onClickRefresh();
    },
});
