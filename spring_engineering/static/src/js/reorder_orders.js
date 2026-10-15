/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { Interaction } from "@web/public/interaction";

// REORDER THE WHOLE ORDER.
//
// The adding is Odoo's own route, which walks the order's lines and puts each
// one in the cart with its attributes, its custom values and its quantity -
// there is no reason to write a second one, and every reason not to. This is
// the button that calls it.
export class ReorderPreviousOrder extends Interaction {
    static selector = ".o_aa_reorder_order";

    dynamicContent = {
        _root: { "t-on-click": this.reorder },
    };

    async reorder(ev) {
        const el = ev.currentTarget;
        const orderId = parseInt(el.dataset.orderId);

        if (!orderId || el.disabled) {
            return;
        }

        // ONE PRESS, NOT THREE. Adding a dozen lines takes a moment, and a
        // button that still looks pressable during it gets pressed again -
        // which would put the order in the cart twice.
        el.disabled = true;

        try {
            await this.waitFor(rpc("/my/orders/reorder", { order_id: orderId }));
        } catch (error) {
            el.disabled = false;
            throw error;
        }

        // RELOADED RATHER THAN PATCHED. The cart's lines, its totals, its
        // delivery and its own reorder panel all change at once; re-rendering
        // the page is both simpler and less likely to leave one of them
        // disagreeing with the rest.
        window.location.reload();
    }
}

registry
    .category("public.interactions")
    .add("spring_engineering.reorder_previous_order", ReorderPreviousOrder);
