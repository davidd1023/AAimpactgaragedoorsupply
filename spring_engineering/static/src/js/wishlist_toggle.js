/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

import { AddProductToWishlistButton } from "@website_sale_wishlist/interactions/add_product_to_wishlist_button";
import wishlistUtils from "@website_sale_wishlist/js/website_sale_wishlist_utils";

// THE HEART HAS TO SAY WHAT IT KNOWS, AND UNDO ITSELF.
//
// Odoo's card button adds a product and then disables itself, so the only way
// off a wishlist is the wishlist page - and the red colour comes from that
// disabled attribute, which this shop drops to keep the button clickable. Two
// things follow, and both are here: the state is painted from the class on
// every page load, and a click on a filled heart removes the product.
patch(AddProductToWishlistButton.prototype, {

    start() {
        const result = super.start?.(...arguments);
        this.aaPaintHeart(this.aaIsWishlisted());

        return result;
    },

    /**
     * Is this card's product on the wishlist?
     *
     * TWO OPINIONS, EITHER OF WHICH IS ENOUGH. The server marks the button
     * when it renders the page, and the browser keeps its own list of product
     * ids. A page served from a cache has the first out of date; a tab that
     * has never loaded the wishlist has the second empty. Trusting both means
     * being wrong only when both are.
     */
    aaIsWishlisted() {
        const productId = parseInt(this.el.dataset.productProductId);

        return Boolean(
            this.el.classList.contains("o_in_wishlist")
            || (productId && wishlistUtils.getWishlistProductIds().includes(productId))
        );
    },

    aaPaintHeart(isWishlisted) {
        const el = this.el;
        el.classList.toggle("o_in_wishlist", isWishlisted);
        // NEVER DISABLED. It is a switch, and a switch that cannot be pressed
        // a second time is a stamp.
        wishlistUtils.updateDisabled(el, false);

        const icon = el.querySelector(".fa");

        if (icon) {
            icon.classList.toggle("fa-heart", isWishlisted);
            icon.classList.toggle("fa-heart-o", !isWishlisted);
        }

        const label = el.querySelector(".o_label");
        const title = isWishlisted ? _t("Remove from wishlist") : _t("Add to wishlist");

        if (label) {
            label.textContent = title;
        }

        el.title = title;
    },

    async addProduct(ev) {
        if (!this.aaIsWishlisted()) {
            await super.addProduct(...arguments);
            // Core disables the button here; this paints the state instead.
            this.aaPaintHeart(true);

            return;
        }

        const productId = parseInt(this.el.dataset.productProductId);

        if (!productId) {
            return;
        }

        // REMOVED BY PRODUCT, not by the row's id, which a product card has no
        // way of knowing. The route finds the row the same way the page that
        // lists it does.
        await this.waitFor(rpc("/shop/wishlist/remove_product", {
            product_id: productId,
        }));
        wishlistUtils.removeWishlistProduct(productId);
        wishlistUtils.updateWishlistNavBar();
        this.aaPaintHeart(false);
    },
});
