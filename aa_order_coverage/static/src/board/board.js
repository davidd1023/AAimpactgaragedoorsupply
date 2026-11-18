/** Orders to Make.
 *
 * Owner, 2026-11-18: "quiero ver las ordenes por hacer y que me salgan segun
 * los filtros que ponga, que podemos hacer y que falta por pedir" - and
 * "por pedir me refiero a que no tengamos".
 *
 * The server hands out the stock first come first served, PER PART, and
 * sends every line. Whether an order can be made for the ticked families is
 * then decided here: it can when none of its lines in those families is
 * short. Each part is allocated on its own, so that answer is exact for any
 * set of families and ticking a box needs no round trip.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class OrderCoverageBoard extends Component {
    static template = "aa_order_coverage.Board";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            data: { families: [], orders: [], lines: [], products: [], next_po: { vendors: [], no_vendor: [] } },
            picked: [], // family ids; none ticked means every family
            show: "all", // all | can | short
            tab: "orders", // orders | missing | nextpo
            search: "",
            open: {}, // seq -> unfolded
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "aa.order.coverage.line", "aa_board_data", []
        );
        this.state.loading = false;
    }

    // ---------------------------------------------------------------- filters
    isPicked(familyId) {
        return this.state.picked.includes(familyId);
    }
    toggleFamily(familyId) {
        const picked = this.state.picked;
        const i = picked.indexOf(familyId);
        if (i >= 0) {
            picked.splice(i, 1);
        } else {
            picked.push(familyId);
        }
    }
    clearFamilies() {
        this.state.picked.splice(0);
    }
    inFamilies(line) {
        const picked = this.state.picked;
        return !picked.length || picked.includes(line.family_id);
    }
    matchesSearch(order) {
        const q = this.state.search.trim().toLowerCase();
        if (!q) {
            return true;
        }
        return [order.wo, order.po, order.customer].join(" ").toLowerCase().includes(q);
    }

    // ----------------------------------------------------------------- orders
    get rows() {
        const bySeq = {};
        for (const line of this.state.data.lines) {
            if (!this.inFamilies(line)) {
                continue;
            }
            (bySeq[line.seq] = bySeq[line.seq] || []).push(line);
        }
        const rows = [];
        for (const order of this.state.data.orders) {
            const lines = bySeq[order.seq];
            if (!lines) {
                continue; // needs nothing of the ticked families
            }
            const short = lines.filter((l) => l.short > 0);
            const row = { ...order, lines, short, canMake: !short.length };
            if (this.state.show === "can" && !row.canMake) {
                continue;
            }
            if (this.state.show === "short" && row.canMake) {
                continue;
            }
            if (!this.matchesSearch(order)) {
                continue;
            }
            rows.push(row);
        }
        return rows;
    }
    get counts() {
        // counted over the families ticked, ignoring the can/short switch
        let can = 0;
        let total = 0;
        let firstShort = null;
        const bySeq = {};
        for (const line of this.state.data.lines) {
            if (this.inFamilies(line)) {
                (bySeq[line.seq] = bySeq[line.seq] || []).push(line);
            }
        }
        for (const order of this.state.data.orders) {
            const lines = bySeq[order.seq];
            if (!lines) {
                continue;
            }
            total++;
            if (lines.some((l) => l.short > 0)) {
                firstShort = firstShort || order;
            } else {
                can++;
            }
        }
        return { can, total, short: total - can, firstShort };
    }
    toggleOpen(seq) {
        this.state.open[seq] = !this.state.open[seq];
    }
    openWorkOrder(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.picking",
            res_id: row.picking_id,
            views: [[false, "form"]],
            target: "current",
        });
    }
    shortText(row) {
        return row.short.map((l) => `${l.product} (${this.fmt(l.short)})`).join(", ");
    }

    // ---------------------------------------------------------- what to order
    get missing() {
        return this.state.data.products.filter(
            (p) => p.missing > 0 && this.inFamilies(p)
        );
    }
    familyName(familyId) {
        const f = this.state.data.families.find((x) => x.id === familyId);
        return f ? f.name : "";
    }

    // ---------------------------------------------------------- the next P.O.
    /* Owner, 2026-11-18: one P.O. per vendor, from the open orders and the
     * pace parts have been used at, waiting here until it is put in Purchase
     * and confirmed. The family chips narrow it like everything else. */
    get vendors() {
        const out = [];
        for (const vendor of this.state.data.next_po.vendors) {
            const lines = vendor.lines.filter((l) => this.inFamilies(l));
            if (lines.length) {
                out.push({ vendor, lines });
            }
        }
        return out;
    }
    get noVendor() {
        return this.state.data.next_po.no_vendor.filter((l) => this.inFamilies(l));
    }
    get nextPoCount() {
        return this.vendors.length;
    }
    vendorTotal(block) {
        return block.lines.reduce((sum, l) => sum + (Number(l.qty) || 0) * l.price, 0);
    }
    money(value) {
        return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
    }
    async saveDays(vendor) {
        await this.orm.call("aa.next.po", "aa_set_vendor_days", [
            vendor.id, Number(vendor.lead) || 0, Number(vendor.cycle) || 0,
        ]);
        await this.load();
    }
    async draftPo(block) {
        const lines = block.lines.map((l) => ({ product_id: l.id, qty: Number(l.qty) || 0 }));
        const po = await this.orm.call("aa.next.po", "aa_draft_po", [block.vendor.id, lines]);
        this.notification.add(`${po.name} saved in Purchase as a draft.`, { type: "success" });
        await this.load();
    }
    openPo(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.order",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    fmt(value) {
        return Number.isInteger(value) ? String(value) : value.toFixed(2);
    }
}

registry.category("actions").add("aa_order_coverage.board", OrderCoverageBoard);
