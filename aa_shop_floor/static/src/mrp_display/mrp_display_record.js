import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

// Tick a row of the card when that piece is in the box. Saved on the
// manufacturing order, so every tablet sees the same ticks.
patch(MrpDisplayRecord.prototype, {
    // THE CARD'S OWN WORDS IN THE USER'S LANGUAGE (owner, 2026-11-11). The
    // rows are stored in English ("Cut to|160\" (LH + RH)"), so the label -
    // and a value that is a fixed phrase - is looked up in i18n/es.po here;
    // anything not listed there (a size, a count) comes back unchanged.
    aaT(text) {
        return text ? String(_t(text)) : text;
    },

    aaPackedKeys() {
        try {
            return JSON.parse(this.props.record.data.aa_packed || "[]");
        } catch {
            return [];
        }
    },

    aaIsPacked(index) {
        return this.aaPackedKeys().includes(String(index));
    },

    aaPackedCount(rows) {
        const keys = this.aaPackedKeys();
        let done = 0;
        let total = 0;
        rows.forEach((row, index) => {
            if (row.split("|")[2] === "c") {
                total++;
                if (keys.includes(String(index))) {
                    done++;
                }
            }
        });
        return total ? done + " / " + total : "";
    },

    // ONE TRACK TASK PER ORDER (owner, 2026-11-02): the other track jobs of
    // this order at this station, drawn inside this card (track_merge.py).
    aaMergePartners() {
        const record = this.props.record;
        if (record.resModel !== "mrp.workorder") {
            return [];
        }
        try {
            return JSON.parse(record.data.aa_track_merge || "{}").partners || [];
        } catch {
            return [];
        }
    },

    aaPartnerIsPacked(partner, index) {
        try {
            return JSON.parse(partner.packed || "[]").includes(String(index));
        } catch {
            return false;
        }
    },

    async aaTogglePartnerPacked(partner, index) {
        await this.model.orm.call("mrp.production", "aa_toggle_packed", [[partner.production_id], String(index)]);
        await this.env.reload(this.props.record);
    },

    async aaTogglePacked(index) {
        const record = this.props.record;
        const productionId =
            record.resModel === "mrp.production" ? record.resId : record.data.production_id.id;
        await this.model.orm.call("mrp.production", "aa_toggle_packed", [[productionId], String(index)]);
        await this.env.reload(record);
    },
});
