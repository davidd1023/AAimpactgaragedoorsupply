/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const ROW_MIN = 34;

function doorFrom(order, door) {
    const w = door.width || 0;
    const ft = Math.floor(w / 12 + 1e-9);
    return {
        order_ref: order.ref, customer: order.customer || "", order: order.order || "",
        feet: w ? String(ft) : "", inches: w ? String(Math.round((w - ft * 12) * 100) / 100) : "",
        height: door.height || 0, panels: door.panels || "",
        locked: Boolean(w && door.panels),
    };
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
            doors: [],
            lookup: "",
            lookupMsg: "",
            block: { side: false, level: false, depth: "both", part: "", note: "" },
            selectedBlock: null,
            spots: [],
            chosen: null,
            suggestInfo: null,
            selected: null,        // bundle id
            moving: null,          // bundle id being moved
            removing: null,        // {bundle} or {door} awaiting the "why"
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
        this.state.doors = [];
        this.state.lookup = "";
        this.state.lookupMsg = "";
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
    async addOrder(ev) {
        if (ev && ev.key && ev.key !== "Enter") {
            return;
        }
        const ref = this.state.lookup.trim();
        if (!ref) {
            return;
        }
        const res = await this.orm.call("aa.door.bundle", "board_lookup", [ref]);
        this.state.spots = [];
        this.state.chosen = null;
        if (res.found && res.doors.length) {
            for (const d of res.doors) {
                this.state.doors.push(doorFrom(res, d));
            }
            const sizesMissing = res.doors.some((d) => !d.width || !d.panels);
            this.state.lookupMsg = `${res.order}: ${res.doors.length} door(s) added` +
                (res.doors.length > 1 ? " - remove any not in this bundle" : "") +
                (sizesMissing ? ". Fill in what is missing." : "") +
                (res.on_rack ? `. ${res.on_rack} already on the racks.` : "");
        } else if (res.found) {
            this.state.doors.push(doorFrom(res, {}));
            this.state.lookupMsg = `${res.order} has no door sizes - type them.`;
        } else {
            this.state.doors.push(doorFrom({ ref: res.ref || ref }, {}));
            this.state.lookupMsg = _t("Not an AA Impact order - type the door size.");
        }
        this.state.lookup = "";
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

    // ---------- closed spots ----------
    blocksFor(side, level, depth) {
        return (this.state.data.blocks || []).filter(
            (b) => b.side === side.id && b.level === level.id && (b.depth === depth || b.depth === "both")
        );
    }
    partsFor(sideId) {
        const side = this.state.data.sides.find((s) => s.id === sideId);
        if (!side) {
            return [];
        }
        const last = side.arms.length - 1;
        return last === 3
            ? [["0-1", "Left"], ["2-3", "Right"], ["0-3", "Whole level"]]
            : [["0-1", "Left"], [`1-${last}`, "Right"], [`0-${last}`, "Whole level"]];
    }
    levelsFor(sideId) {
        const side = this.state.data.sides.find((s) => s.id === sideId);
        return side ? side.levels : [];
    }
    startBlock() {
        this.cancel();
        this.state.selected = null;
        const side = this.state.data.sides[0];
        this.state.block = { side: side && side.id, level: side && side.levels.at(-1).id,
                             depth: "both", part: "0-1", note: "" };
        this.state.mode = "block";
    }
    onBlockSide(ev) {
        const id = parseInt(ev.target.value);
        this.state.block.side = id;
        this.state.block.level = this.levelsFor(id).at(-1).id;
        this.state.block.part = "0-1";
    }
    async saveBlock() {
        const b = this.state.block;
        const [a, z] = b.part.split("-").map((x) => parseInt(x));
        await this.orm.call("aa.door.bundle", "board_block", [{
            level: parseInt(b.level), depth: b.depth, arm_from: a, arm_to: z, note: b.note,
        }]);
        this.cancel();
        await this.load();
        this.notification.add(_t("Spot closed."), { type: "success" });
    }
    selectBlock(block) {
        if (this.state.mode !== "view") {
            return;
        }
        this.state.selected = null;
        this.state.selectedBlock = this.state.selectedBlock === block.id ? null : block.id;
    }
    get selectedBlockData() {
        return (this.state.data.blocks || []).find((b) => b.id === this.state.selectedBlock);
    }
    async unblock(id) {
        await this.orm.call("aa.door.bundle", "board_unblock", [id]);
        this.state.selectedBlock = null;
        await this.load();
    }

    // ---------- a bundle ----------
    selectBundle(id) {
        if (this.state.mode !== "view") {
            return;
        }
        this.state.selectedBlock = null;
        this.state.selected = this.state.selected === id ? null : id;
    }
    async startMove(id) {
        this.state.mode = "move";
        this.state.moving = id;
        await this.suggest([], id);
    }
    askRemove(what) {
        this.state.removing = what;
    }
    isRemoving(kind, id) {
        const r = this.state.removing;
        return r && r[kind] === id;
    }
    async remove(mode) {
        const r = this.state.removing;
        this.state.removing = null;
        await this.orm.call("aa.door.bundle", "board_remove", [r.bundle || false, r.door ? [r.door] : [], mode]);
        const keep = this.state.selected;
        await this.load();
        this.state.selected = this.state.data.bundles.some((b) => b.id === keep) ? keep : null;
        this.notification.add(mode === "mistake" ? _t("Deleted.") : _t("Taken off the rack."), { type: "success" });
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
