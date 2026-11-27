import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

// THE HARDWARE BOX, ONE PIECE AT A TIME (owner, 2026-11-27: "que se entienda
// mas, paso a paso en vez de listarlo todo, y siempre dar un boton de
// confirmacion que se echo en la caja y automatico al next, y ademas puede ir
// atras y ver alguna cosa que hecho, y la info del cable al final").
//
// The same rows and the same ticks as the list (aa_packed, aa_toggle_packed),
// so the two views always agree and every tablet sees the same progress. The
// whole list is still one button away.

patch(MrpDisplayRecord.prototype, {
    setup() {
        super.setup();
        this.aaStepUi = useState({ cursor: null, showList: false });
    },

    aaPackSteps() {
        // A card that cannot be worked out falls back to the plain list: one
        // bad card must never take the Shop Floor down.
        try {
            return this._aaPackSteps();
        } catch {
            return null;
        }
    },

    _aaPackSteps() {
        const record = this.props.record;
        if (record.resModel !== "mrp.workorder" || !record.data.aa_shop_spec) {
            return null;
        }
        const rows = record.data.aa_shop_spec.split("\n").map((r) => r.split("|"));
        const boxAt = rows.findIndex((p) => p[0] === "Box contents" && !p[1]);
        if (boxAt < 0) {
            return null;
        }
        const header = rows.slice(0, boxAt).filter((p) => p[1]);
        const steps = [];
        rows.forEach((p, index) => {
            if (index <= boxAt || p[2] !== "c") {
                return;
            }
            const step = { index, name: p[0], qty: p[1] || "", details: [] };
            if (!p[1]) {
                // A section to tick (the lift cable): its detail rows follow.
                for (let j = index + 1; j < rows.length && rows[j][1] && rows[j][2] !== "c"; j++) {
                    step.details.push(rows[j]);
                }
            }
            steps.push(step);
        });
        if (!steps.length) {
            return null;
        }
        const packed = this.aaPackedKeys();
        steps.forEach((s) => (s.done = packed.includes(String(s.index))));
        const doneCount = steps.filter((s) => s.done).length;
        let pos = steps.findIndex((s) => s.index === this.aaStepUi.cursor);
        if (pos < 0) {
            pos = steps.findIndex((s) => !s.done);
        }
        const allDone = doneCount === steps.length;
        return {
            header,
            steps,
            doneCount,
            allDone,
            pos: pos < 0 ? steps.length - 1 : pos,
            showSummary: allDone && this.aaStepUi.cursor === null,
        };
    },

    aaStepGo(steps, pos) {
        const clamped = Math.max(0, Math.min(steps.length - 1, pos));
        this.aaStepUi.cursor = steps[clamped].index;
    },

    async aaStepConfirm(info) {
        const step = info.steps[info.pos];
        // Next: the first piece after this one still to go in, else any before it.
        const after = info.steps.slice(info.pos + 1).find((s) => !s.done);
        const before = info.steps.slice(0, info.pos).find((s) => !s.done);
        const next = after || before;
        this.aaStepUi.cursor = next ? next.index : null;
        if (!step.done) {
            await this.aaTogglePacked(step.index);
        }
    },

    async aaStepUndo(info) {
        const step = info.steps[info.pos];
        this.aaStepUi.cursor = step.index;
        if (step.done) {
            await this.aaTogglePacked(step.index);
        }
    },

    aaStepToggleList() {
        this.aaStepUi.showList = !this.aaStepUi.showList;
    },
});
