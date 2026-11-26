import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { AaTrackSwapDialog } from "./track_swap";

// JORGE'S TRACK CARD, STRAIGHT TO THE POINT (owner, 2026-11-26). Each track
// job on a Track Prep card - this one and the order's others drawn on it -
// as: which RAW track to take (with Change right there), what to cut it to,
// the lift, and the jamb brackets per vertical. The data is the server's
// (track_card.py); this only draws it.

function parse(text) {
    try {
        return text ? JSON.parse(text) : null;
    } catch {
        return null;
    }
}

patch(MrpDisplayRecord.prototype, {
    aaTrackCards() {
        const record = this.props.record;
        if (record.resModel !== "mrp.workorder") {
            return null;
        }
        const own = parse(record.data.aa_track_card);
        if (!own) {
            return null;
        }
        const cards = [{ key: "own", productionId: this.aaProductionId(), card: own }];
        for (const partner of this.aaMergePartners()) {
            const card = parse(partner.card);
            if (card && !cards.some((c) => c.productionId === partner.production_id)) {
                cards.push({ key: String(partner.id), productionId: partner.production_id, card });
            }
        }
        // Vertical first, then horizontal: the order they go up the wall.
        cards.sort((a, b) => (a.card.kind === b.card.kind ? 0 : a.card.kind === "vertical" ? -1 : 1));
        return cards;
    },

    aaTrackOpen() {
        return !["done", "cancel"].includes(this.props.record.data.state);
    },

    aaChangeTrack(productionId) {
        const record = this.props.record;
        this.aaDialog.add(AaTrackSwapDialog, {
            productionIds: [productionId],
            onDone: () => this.env.reload(record),
        });
    },
});
