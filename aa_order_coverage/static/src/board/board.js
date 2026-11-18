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
            data: { families: [], orders: [], lines: [], products: [], next_po: { vendors: [], no_vendor: [] }, capacity: {} },
            cap: { tracks: 6, boxes: 10 },
            plan: {}, // seq -> {date, noPo, partsBy}
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
        for (const vendor of this.state.data.next_po.vendors) {
            this.setCoils(vendor);
        }
        this.state.cap = { ...this.state.data.capacity };
        this.schedule();
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
            // WHEN WILL IT BE READY: worked out over the whole order, every
            // part and the shop's daily capacity (see schedule()), so the
            // date does not change with the family chips ticked.
            const plan = this.state.plan[order.seq] || {};
            row.noPo = plan.noPo;
            row.partsBy = plan.partsBy || "";
            row.finishBy = plan.date || "";
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
    // ------------------------------------------------------------ the plan
    /* Owner, 2026-11-18: "hacemos 6-9 tracks al dia, y 10 a 15 cajas de
     * hardware con sus muelles, dame una fecha mas realistica". Each order
     * can start once ALL its parts are in (today, or the working day after
     * the last confirmed P.O. it waits for lands); the track bench and the
     * hardware bench then work through the orders in the order they become
     * ready, oldest first among equals, each at its own daily rate. An order
     * is ready the working day both of its benches finish it. An order
     * missing a part nobody has ordered is left out and takes no capacity. */
    workdayIndex(iso) {
        // working days from today to the working day AFTER iso
        const today = this.today();
        let d = new Date(iso + "T12:00:00");
        let n = 0;
        const cur = new Date(today + "T12:00:00");
        while (cur <= d) {
            cur.setDate(cur.getDate() + 1);
            if (cur.getDay() !== 0 && cur.getDay() !== 6) {
                n++;
            }
        }
        return n;
    }
    workdayDate(index) {
        const d = new Date(this.today() + "T12:00:00");
        while (d.getDay() === 0 || d.getDay() === 6) {
            d.setDate(d.getDate() + 1);
        }
        let n = index;
        while (n > 0) {
            d.setDate(d.getDate() + 1);
            if (d.getDay() !== 0 && d.getDay() !== 6) {
                n--;
            }
        }
        return d.toISOString().slice(0, 10);
    }
    today() {
        const d = new Date();
        const pad = (x) => String(x).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }
    schedule() {
        const perTrack = Number(this.state.cap.tracks) || 6;
        const perBox = Number(this.state.cap.boxes) || 10;
        const bySeq = {};
        for (const line of this.state.data.lines) {
            (bySeq[line.seq] = bySeq[line.seq] || []).push(line);
        }
        const plan = {};
        const queue = [];
        for (const order of this.state.data.orders) {
            const short = (bySeq[order.seq] || []).filter((l) => l.short > 0);
            const etas = short.map((l) => l.eta);
            if (etas.some((e) => !e)) {
                plan[order.seq] = { noPo: true };
                continue;
            }
            const partsBy = etas.length ? etas.sort().at(-1) : "";
            const ready = partsBy ? this.workdayIndex(partsBy) : 0;
            queue.push({ order, ready, partsBy });
        }
        queue.sort((a, b) => a.ready - b.ready || a.order.seq - b.order.seq);
        let trackAt = 0;
        let boxAt = 0;
        for (const { order, ready, partsBy } of queue) {
            let done = ready;
            if (order.tracks > 0) {
                trackAt = Math.max(trackAt, ready) + order.tracks / perTrack;
                done = Math.max(done, Math.ceil(trackAt - 1e-9) - 1);
            }
            if (order.boxes > 0) {
                boxAt = Math.max(boxAt, ready) + order.boxes / perBox;
                done = Math.max(done, Math.ceil(boxAt - 1e-9) - 1);
            }
            plan[order.seq] = { date: this.workdayDate(Math.max(done, ready)), partsBy };
        }
        this.state.plan = plan;
    }
    async saveCapacity() {
        await this.orm.call("aa.order.coverage.line", "aa_set_capacity", [
            Number(this.state.cap.tracks), Number(this.state.cap.boxes),
        ]);
        this.schedule();
    }
    addWorkdays(iso, n) {
        const d = new Date(iso + "T12:00:00");
        while (n > 0) {
            d.setDate(d.getDate() + 1);
            if (d.getDay() !== 0 && d.getDay() !== 6) {
                n--;
            }
        }
        return d.toISOString().slice(0, 10);
    }
    dotClass(row) {
        if (row.canMake) {
            return "text-success";
        }
        return row.noPo ? "text-danger" : "text-warning";
    }
    comingText(line) {
        return line.coming.map((c) => `${c.po}: ${this.fmt(c.qty)} on ${c.date || "?"}`).join(", ");
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
    // SPRING COIL: ordered as whole coils ("serpientes") of 7 or 8 ft,
    // picked per vendor; the inches still to cover set how many.
    hasCoils(block) {
        return block.lines.some((l) => l.coil);
    }
    setCoils(vendor) {
        const inches = (vendor.coil_feet || 7) * 12;
        for (const line of vendor.lines) {
            if (line.coil) {
                line.coils = Math.max(Math.ceil(line.need_in / inches - 1e-6), 1);
            }
        }
    }
    async changeCoilFeet(vendor, ev) {
        vendor.coil_feet = Number(ev.target.value);
        this.setCoils(vendor);
        await this.orm.call("aa.next.po", "aa_set_coil_feet", [vendor.id, vendor.coil_feet]);
    }
    coilInches(p, v) {
        return (Number(p.coils) || 0) * v.coil_feet * 12;
    }
    // Templates cannot reach Number or Math: the arithmetic lives here.
    lineTotal(p, v) {
        if (p.coil && v) {
            return this.coilInches(p, v) * p.price;
        }
        return (Number(p.qty) || 0) * p.price;
    }
    perMonth(p) {
        return p.per_month ? this.fmt(Math.round(p.per_month * 10) / 10) : "";
    }
    vendorTotal(block) {
        return block.lines.reduce((sum, l) => sum + this.lineTotal(l, block.vendor), 0);
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
        const v = block.vendor;
        const lines = block.lines.map((l) =>
            l.coil
                ? { product_id: l.id, coils: Number(l.coils) || 0, feet: v.coil_feet }
                : { product_id: l.id, qty: Number(l.qty) || 0 }
        );
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
