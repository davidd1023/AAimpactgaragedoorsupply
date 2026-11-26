/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { _t } from "@web/core/l10n/translation";

const ROW_MIN = 34;

function doorFrom(order, door) {
    const w = door.width || 0;
    const ft = Math.floor(w / 12 + 1e-9);
    return {
        order_ref: order.ref, door_no: door.door_no || 0, customer: order.customer || "", order: order.order || "",
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
            lookupLevel: "info",
            bundleSize: 0,         // 1 = single, 2 = double; one sticker scanned per door
            block: { picked: [], note: "" },
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
        return this.spotLabel(this.state.chosen);
    }
    spotLabel(c) {
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
        this.state.bundleSize = 0;
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
    chooseSize(n) {
        this.state.bundleSize = n;
        this.state.doors = [];
        this.state.spots = [];
        this.state.chosen = null;
        this.state.lookupMsg = "";
        this.focusScan();
    }
    focusScan() {
        setTimeout(() => document.querySelector(".o_rack_scan input")?.focus(), 60);
    }
    get scanDone() {
        return this.state.bundleSize && this.state.doors.length >= this.state.bundleSize;
    }
    async scan(ev) {
        if (ev && ev.key && ev.key !== "Enter") {
            return;
        }
        const code = this.state.lookup.trim();
        this.state.lookup = "";
        if (!code || this.scanDone) {
            return;
        }
        const taken = this.state.doors.map((d) => ({ order_ref: d.order_ref, door_no: d.door_no }));
        const res = await this.orm.call("aa.door.bundle", "board_scan", [code, taken]);
        this.state.lookupMsg = res.msg || "";
        this.state.lookupLevel = res.level || "info";
        if (res.ok) {
            const d = res.door;
            this.state.doors.push(doorFrom({ ref: d.order_ref, customer: d.customer, order: d.order }, d));
            this.state.spots = [];
            this.state.chosen = null;
            const ready = this.scanDone && this.state.doors.every((x) => x.locked);
            if (ready) {
                await this.findSpot();
                return;
            }
        }
        this.focusScan();
    }
    get cameraOk() {
        return isBarcodeScannerSupported();
    }
    async scanCamera() {
        let code;
        try {
            code = await scanBarcode(this.env);
        } catch {
            this.notification.add(_t("No camera could be opened. Use a scanner or type the AA order #."), { type: "warning" });
            return;
        }
        if (code) {
            this.state.lookup = code;
            await this.scan();
        }
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
            door_no: d.door_no || 0,
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
    // A row is closed by halves: the two cantilever units of A-D (arms 0-1
    // and 2-3; the 60" gap between them holds nothing on its own) and the two
    // bays of E (arms 0-1, 1-2).
    unitsFor(side) {
        const last = side.arms.length - 1;
        return last === 3 ? [[0, 1], [2, 3]] : [[0, 1], [1, last]];
    }
    cellsFor(side, level, depth) {
        return this.unitsFor(side).map(([a, b]) => {
            const start = a === 0 ? side.min : side.arms[a] - 1;
            const end = b === side.arms.length - 1 ? side.max : side.arms[b] + 1;
            return { key: `${level.id}|${depth}|${a}-${b}`, side: side.id, level: level.id, depth,
                     arm_from: a, arm_to: b, start, length: end - start,
                     busy: this.cellBusy(side, level, depth, a, b) };
        });
    }
    cellBusy(side, level, depth, a, b) {
        const hit = (x) => x.arm_from <= b && x.arm_to >= a;
        if ((this.state.data.blocks || []).some((x) => x.level === level.id &&
                (x.depth === depth || x.depth === "both") && hit(x))) {
            return "closed";
        }
        if (this.state.data.bundles.some((x) => x.level === level.id && x.depth === depth && hit(x))) {
            return "doors";
        }
        return false;
    }
    isPicked(cell) {
        return this.state.block.picked.includes(cell.key);
    }
    togglePick(cells) {
        const free = cells.filter((c) => !c.busy);
        if (!free.length) {
            return;
        }
        const picked = this.state.block.picked;
        const allOn = free.every((c) => picked.includes(c.key));
        for (const c of free) {
            const i = picked.indexOf(c.key);
            if (allOn && i >= 0) {
                picked.splice(i, 1);
            } else if (!allOn && i < 0) {
                picked.push(c.key);
            }
        }
    }
    pickCell(cell) {
        this.togglePick([cell]);
    }
    pickLevel(side, level) {
        if (this.state.mode !== "block") {
            return;
        }
        this.togglePick(["back", "front"].flatMap((d) => this.cellsFor(side, level, d)));
    }
    pickSide(side) {
        if (this.state.mode !== "block") {
            return;
        }
        this.togglePick(side.levels.flatMap((lv) =>
            ["back", "front"].flatMap((d) => this.cellsFor(side, lv, d))));
    }
    startBlock() {
        this.cancel();
        this.state.selected = null;
        this.state.selectedBlock = null;
        this.state.block = { picked: [], note: "" };
        this.state.mode = "block";
    }
    get pickedSummary() {
        const codes = {};
        for (const key of this.state.block.picked) {
            const level = parseInt(key.split("|")[0]);
            for (const side of this.state.data.sides) {
                const lv = side.levels.find((l) => l.id === level);
                if (lv) {
                    codes[lv.code] = true;
                }
            }
        }
        return Object.keys(codes).sort().join(", ");
    }
    async saveBlock() {
        const spots = this.state.block.picked.map((key) => {
            const [level, depth, arms] = key.split("|");
            const [a, b] = arms.split("-").map((x) => parseInt(x));
            return { level: parseInt(level), depth, arm_from: a, arm_to: b };
        });
        if (!spots.length) {
            this.notification.add(_t("Click the spots to close first."), { type: "warning" });
            return;
        }
        await this.orm.call("aa.door.bundle", "board_block_many", [spots, this.state.block.note]);
        this.cancel();
        await this.load();
        this.notification.add(_t("Closed."), { type: "success" });
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
