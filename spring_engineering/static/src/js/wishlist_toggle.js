/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";

import { AddProductToWishlistButton } from "@website_sale_wishlist/interactions/add_product_to_wishlist_button";
import wishlistUtils from "@website_sale_wishlist/js/website_sale_wishlist_utils";

// THE HEART IS A SWITCH: red when the product is on the list, and a click on a
// red one takes it off.
//
// REPLACED RATHER THAN PATCHED, and the difference is the bug the owner hit.
// Odoo's interaction binds its click handler like this:
//
//     dynamicContent = { _root: { 't-on-click': this.addProduct } };
//
// That is a class FIELD: it reads `this.addProduct` once, when the instance is
// built, and keeps the function it found. Patching the prototype afterwards
// changes nothing for an instance that already exists - it is still holding
// the original. So whether a heart could be un-clicked came down to whether
// this file happened to run before the buttons on that page were wired up,
// which is exactly the shape of the report: it worked, then after walking to
// another page and back the same hearts were stuck red, because Odoo's own
// handler was the one listening and it returns early for a product already on
// the list.
//
// Taking Odoo's registration out and putting this subclass in its place leaves
// exactly one handler on the button, and it is this one, every time.
export class WishlistHeart extends AddProductToWishlistButton {

    start() {
        const result = super.start?.(...arguments);
        this.paintHeart(this.isWishlisted());

        return result;
    }

    /**
     * Is this card's product on the wishlist?
     *
     * TWO OPINIONS, EITHER OF WHICH IS ENOUGH. The server marks the button
     * when it renders the page, and the browser keeps its own list of product
     * ids. A page served from a cache has the first out of date; a tab that
     * has never loaded the wishlist has the second empty. Trusting both means
     * being wrong only when both are.
     */
    isWishlisted() {
        const productId = parseInt(this.el.dataset.productProductId);

        return Boolean(
            this.el.classList.contains("o_in_wishlist")
            || (productId && wishlistUtils.getWishlistProductIds().includes(productId))
        );
    }

    paintHeart(isWishlisted) {
        const el = this.el;
        el.classList.toggle("o_in_wishlist", isWishlisted);
        // NEVER DISABLED. Odoo disables the button once the product is on the
        // list - which is also how it colours it red - and a disabled button
        // swallows the click that would take the product off again.
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
    }

    async addProduct(ev) {
        if (!this.isWishlisted()) {
            await super.addProduct(...arguments);
            // Core disables the button here; this paints the state instead.
            this.paintHeart(true);

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
        this.paintHeart(false);
        this.showRemoved();
    }

    /**
     * Say, visibly, that the product came off the list.
     *
     * ADDING ANIMATES AND REMOVING DID NOT - Odoo flies a copy of the product
     * up to the navbar when something goes on the list, and taking it off
     * changed nothing a pointer could see. Worse, the pointer is still ON the
     * heart when the click lands, and the hover rule fills an empty heart red
     * to show what clicking WOULD do: so a removal left a red heart under the
     * cursor, looking exactly like a click that had not worked.
     *
     * The class drives both the shrink and the suppression of that preview,
     * and it is dropped when the pointer leaves, so the next hover previews
     * normally.
     */
    showRemoved() {
        const el = this.el;
        el.classList.add("o_aa_wish_removed");

        const clear = () => {
            el.classList.remove("o_aa_wish_removed");
            el.removeEventListener("mouseleave", clear);
        };

        el.addEventListener("mouseleave", clear);
    }
}

const interactions = registry.category("public.interactions");
const CORE = "website_sale_wishlist.add_product_to_wishlist_button";

// Guarded: if Odoo ever renames or drops that registration, this still
// installs a working heart rather than throwing on the way in.
if (interactions.contains(CORE)) {
    interactions.remove(CORE);
}

interactions.add("spring_engineering.wishlist_heart", WishlistHeart);
