/** @odoo-module **/
// THE BOARD HEARS ABOUT A CANCEL (owner, 2026-10-19: "when i cancel an order
// in manufacturing it doesnt automatically cancel it in shop floor").
//
// The cancel always worked; nothing told the tablet. The Shop Floor loads its
// records once and reloads only when something inside it asks - a button, a
// dialog closing, a barcode - so a job cancelled from the Manufacturing app
// stayed on the board until somebody pressed Reload Data.
//
// The server now sends "look again" to the shop floor's own users when a job
// is cancelled (see models/shop_floor_live.py) and this is the ear for it.

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { MrpDisplay } from "@mrp_workorder/mrp_display/mrp_display";

// COALESCED, because cancelling five jobs sends five notifications and the
// board only needs to look again once. Long enough to gather a burst, short
// enough that nobody watching notices the wait.
const SETTLE_MS = 800;

patch(MrpDisplay.prototype, {
    setup() {
        super.setup();
        this.aaLiveBus = useService("bus_service");
        this.aaLiveTimer = null;

        this.aaLiveBus.subscribe("aa_shop_floor_changed", () => {
            clearTimeout(this.aaLiveTimer);
            this.aaLiveTimer = setTimeout(() => {
                // THE SAME RELOAD THE MENU DOES, so there is one way for this
                // page to bring itself up to date rather than two that can
                // behave differently. Guarded because the notification can
                // land after somebody has closed the page.
                try {
                    this.onClickRefresh();
                } catch {
                    // The board is gone; there is nothing to refresh.
                }
            }, SETTLE_MS);
        });
    },
});
