/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

const ROW_MIN = 34;

function newDoor() {
    return { order_ref: "", customer: "", feet: "", inches: "", panels: 4 };
}

function feetLabel(inches) {
    const ft = Math.floor(inches / 12 + 1e-9);
    const rest = Math.round((inches - ft * 12) * 100) / 100;
    return rest ? `${ft}' ${rest}"` : `${ft}'`;
}

export class RackBoard extends Component {
    static template = "aa_door_racks.RackBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.state = useState({
            loading: true,
            data: { sides: [], bundles: [], free: {}, admin: false },
            term: "",
            results: null,
            highlight: [],
            mode: "view",          // view | receive | move
            doors: [newDoor()],
            spots: [],
            chosen: null,
            suggestInfo: null,
            selected: null,        // bundle id
            moving: null,          // bundle id being moved
        });
        this.feetLabel = feetLabel;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("aa.door.bundle", "board_data", []);
        this.state.loading = false;
    }

    // ---------- geometry ----------
    pct(side, x) {
        return ((x - side.min) / (side.max - side.min)) * 100;
    }
    armStyle(side, arm) {
        return `left: ${this.pct(side, arm)}%;`;
    }
    boxStyle(side, start, length) {
        return `left: ${this.pct(side, start)}%; width: ${(length / (side.max - side.min)) * 100}%;`;
    }
    stacksFor(side, level, depth) {
        const members = this.state.data.bundles.filter(
            (b) => b.side === side.id && b.level === level.id && b.depth === depth
        );
        const groups = {};
        for (const b of members) {
            const key = `${b.arm_from}-${b.arm_to}`;
            (groups[key] = groups[key] || []).push(b);
        }
        return Object.values(groups).map((list) => {
            list.sort((a, b) => b.seq - a.seq);   // top of the stack first
            const start = Math.min(...list.map((b) => b.start));
            const end = Math.max(...list.map((b) => b.start + b.length));
            const height = list.reduce((s, b) => s + b.height, 0) +
                (list.length - 1) * (this.state.data.rules?.spacer || 1.5);
            return { key: `${level.id}-${depth}-${list[0].arm_from}`, start, length: end - start, bundles: list, height };
        });
    }
    spotsFor(side, level, depth) {
        return this.state.spots.filter(
            (s) => s.side === side.id && s.level === level.id && s.depth === depth
        );
    }
    rowStyle(side, level, depth) {
        const stacks = this.stacksFor(side, level, depth);
        const most = Math.max(0, ...stacks.map((s) => s.bundles.length));
        return `min-height: ${Math.max(ROW_MIN, most * 22 + 8)}px;`;
    }
    isChosen(spot) {
        const c = this.state.chosen;
        return c && c.side === spot.side && c.level === spot.level && c.depth === spot.depth &&
            c.arm_from === spot.arm_from && c.arm_to === spot.arm_to;
    }
    levelFill(side, level) {
        if (!level.clearance) {
            return _t("no height limit");
        }
        return `${level.clearance}"`;
    }
    get selectedBundle() {
        return this.state.data.bundles.find((b) => b.id === this.state.selected);
    }
    get chosenLabel() {
        const c = this.state.chosen;
        if (!c) {
            return "";
        }
        const side = this.state.data.sides.find((s) => s.id === c.side);
        const n = side ? side.arms.length : 0;
        const names = n === 4
            ? { "0-1": "Left", "2-3": "Right", "1-2": "Middle", "0-2": "Full (arms 1-3)", "1-3": "Full (arms 2-4)" }
            : { "0-1": "Left", "1-2": "Right", "0-2": "Full" };
        const where = names[`${c.arm_from}-${c.arm_to}`] || "";
        return `${c.level_code} · ${where} · ${c.depth === "back" ? "Back" : "Front"}` +
            (c.stacked ? ` · on top (stack ${c.stack_height}")` : "");
    }

    // ---------- search ----------
    async onSearch(ev) {
        this.state.term = ev.target.value;
        if (ev.key && ev.key !== "Enter") {
            return;
        }
        const term = this.state.term.trim();
        if (!term) {
            this.state.results = null;
            this.state.highlight = [];
            return;
        }
        const res = await this.orm.call("aa.door.bundle", "board_search", [term]);
        this.state.results = res;
        this.state.highlight = res.map((d) => d.bundle);
        if (res.length) {
            const el = document.querySelector(`[data-bundle="${res[0].bundle}"]`);
            el?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }
    clearSearch() {
        this.state.term = "";
        this.state.results = null;
        this.state.highlight = [];
    }

    // ---------- receive ----------
    startReceive() {
        this.state.mode = "receive";
        this.state.doors = [newDoor()];
        this.state.spots = [];
        this.state.chosen = null;
        this.state.selected = null;
        this.state.suggestInfo = null;
    }
    cancel() {
        this.state.mode = "view";
        this.state.spots = [];
        this.state.chosen = null;
        this.state.moving = null;
        this.state.suggestInfo = null;
    }
    addDoor() {
        this.state.doors.push(newDoor());
        this.state.spots = [];
        this.state.chosen = null;
    }
    removeDoor(idx) {
        this.state.doors.splice(idx, 1);
        this.state.spots = [];
        this.state.chosen = null;
    }
    onDoorInput() {
        this.state.spots = [];
        this.state.chosen = null;
    }
    doorPayload() {
        return this.state.doors.map((d) => ({
            order_ref: d.order_ref,
            customer: d.customer,
            width: (parseFloat(d.feet) || 0) * 12 + (parseFloat(d.inches) || 0),
            panels: parseInt(d.panels) || 0,
        }));
    }
    async findSpot() {
        const doors = this.doorPayload();
        if (doors.some((d) => !d.order_ref.trim() || !d.width || !d.panels)) {
            this.notification.add(_t("Every door needs its order #, width and panels."), { type: "warning" });
            return;
        }
        await this.suggest(doors, false);
    }
    async suggest(doors, bundleId) {
        const res = await this.orm.call("aa.door.bundle", "board_suggest", [doors, bundleId]);
        this.state.spots = res.spots;
        this.state.chosen = res.spots[0] || null;
        this.state.suggestInfo = { length: res.length, height: res.height };
        if (!res.spots.length) {
            this.notification.add(_t("There is no room on the racks for this bundle."), { type: "danger" });
        } else {
            const el = document.querySelector(".o_rack_spot.o_best");
            setTimeout(() => document.querySelector(".o_rack_spot.o_chosen")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
        }
    }
    chooseSpot(spot) {
        this.state.chosen = spot;
    }
    async saveHere() {
        const spot = this.state.chosen;
        if (!spot) {
            return;
        }
        if (this.state.mode === "receive") {
            const bundle = await this.orm.call("aa.door.bundle", "board_receive", [this.doorPayload(), spot]);
            this.notification.add(`${bundle.name} → ${bundle.location}`, { type: "success" });
            this.cancel();
            await this.load();
            this.state.selected = bundle.id;
        } else if (this.state.mode === "move") {
            await this.orm.call("aa.door.bundle", "board_move", [this.state.moving, spot]);
            const id = this.state.moving;
            this.cancel();
            await this.load();
            this.state.selected = id;
            this.notification.add(_t("Moved."), { type: "success" });
        }
    }

    // ---------- a bundle ----------
    selectBundle(id) {
        if (this.state.mode !== "view") {
            return;
        }
        this.state.selected = this.state.selected === id ? null : id;
    }
    async startMove(id) {
        this.state.mode = "move";
        this.state.moving = id;
        await this.suggest([], id);
    }
    deliver(door) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Mark the door of order %s as delivered? It leaves the rack.", door.order_ref),
            confirm: async () => {
                await this.orm.call("aa.door.bundle", "board_deliver", [[door.id]]);
                await this.load();
            },
            cancel: () => {},
        });
    }
    async splitDoor(door) {
        const bundle = await this.orm.call("aa.door.bundle", "board_split", [door.id]);
        await this.load();
        this.state.selected = null;
        this.state.mode = "move";
        this.state.moving = bundle.id;
        await this.suggest([], bundle.id);
        this.notification.add(_t("Order %s is now %s - pick its new spot.", door.order_ref, bundle.name), { type: "info" });
    }
    printLabel(id) {
        this.action.doAction("aa_door_racks.report_bundle_label", {
            additionalContext: { active_ids: [id], active_id: id, active_model: "aa.door.bundle" },
        });
    }
    openBundle(id) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "aa.door.bundle", res_id: id,
            views: [[false, "form"]], target: "current",
        });
    }
}

registry.category("actions").add("aa_door_racks.board", RackBoard);
