/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebsiteSale } from "@website_sale/interactions/website_sale";

// THE PARTS TRAVEL WITH THE CART REQUEST.
//
// This file exists because of the owner's own question, 2026-10-20: "maybe you
// should try finding out why the other kits work and this one doesnt". That is
// the right question, and this is the answer.
//
// An ordinary AA kit's extras are ticked product attributes. They are posted
// IN the Add to Cart request, so the server reads them off what the browser
// has just sent, and they have always worked. A custom kit's parts were posted
// EARLIER, to the pricing route, and held in the session - and on production
// that list was not there any more by the time the cart request ran.
//
// Measured rather than guessed: a cart add that books thirteen parts costs 271
// queries, an empty one 89, and production's was 78. The packing never even
// started, so every fix aimed further downstream - the popup, the pricing
// order, the out-of-stock rule - was aimed at the wrong thing.
//
// Odoo builds its cart request from `rootProduct` and forwards every key it
// does not recognise straight through to the controller, so adding one key
// here is all it takes to send the kit the same way the working kits send
// theirs. The page keeps the list in a data attribute, written before the
// pricing call rather than after it comes back, so the cart carries the kit
// even when that call never lands. The session is still written and still read
// as a fallback; this is simply the path that cannot lose anything in
// between.
patch(WebsiteSale.prototype, {
    _updateRootProduct(form) {
        super._updateRootProduct(form);
        const root = document.getElementById("aa_custom_kit");

        if (root && root.dataset.aaParts) {
            this.rootProduct.aa_custom_parts = root.dataset.aaParts;
        }
    },
});
