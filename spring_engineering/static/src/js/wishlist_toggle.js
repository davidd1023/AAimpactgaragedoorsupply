/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

import wishlistUtils from "@website_sale_wishlist/js/website_sale_wishlist_utils";

// THE HEART IS A SWITCH, AND IT DOES NOT DEPEND ON WHEN ANYTHING ELSE LOADED.
//
// Two attempts at this failed in the same way, and both failed for reasons of
// ORDER rather than of logic:
//
//   patching the prototype  Odoo binds its handler with a class FIELD -
//                           dynamicContent = { _root: { 't-on-click':
//                           this.addProduct } } - which reads the function
//                           once, when the button is wired up. A patch that
//                           lands afterwards is simply not the function that
//                           button is holding.
//
//   replacing the registry  the public.interactions service reads the registry
//                           ONCE, in its start(), and keeps the list:
//                           `this.Interactions = Interactions`. Nothing
//                           re-reads it. A swap that happens after that start
//                           changes nothing on that page.
//
// Both are races this file cannot win by trying harder, and the symptom was
// the same each time: hearts that worked, then after walking to another page
// and back were stuck red, because Odoo's own handler was the one listening -
// and it returns early for a product already on the list.
//
// So this listens on the DOCUMENT, in the CAPTURE phase. A capture listener on
// the document runs before any listener on the button itself, whoever bound it
// and whenever: the click is handled here and stopped before it reaches
// Odoo's. There is no registration to be late for and no instance to be
// holding the wrong function.
const BUTTON = ".o_add_wishlist";

function productOf(el) {
    return parseInt(el.dataset.productProductId) || 0;
}

/**
 * Is this card's product on the wishlist?
 *
 * TWO OPINIONS, EITHER OF WHICH IS ENOUGH. The server marks the button when it
 * renders the page, and the browser keeps its own list of product ids. A page
 * from a cache has the first out of date; a tab that never loaded the wishlist
 * has the second empty. Reading both means being wrong only when both are.
 */
function isWishlisted(el) {
    const productId = productOf(el);

    return Boolean(
        el.classList.contains("o_in_wishlist")
        || (productId && wishlistUtils.getWishlistProductIds().includes(productId))
    );
}

function paint(el, wishlisted) {
    el.classList.toggle("o_in_wishlist", wishlisted);
    // NEVER DISABLED. Odoo disables the button once the product is on the list
    // - which is also how it colours it red - and a disabled button swallows
    // the very click that would take the product off again.
    el.disabled = false;
    el.classList.remove("disabled");

    const icon = el.querySelector(".fa");

    if (icon) {
        icon.classList.toggle("fa-heart", wishlisted);
        icon.classList.toggle("fa-heart-o", !wishlisted);
    }

    const title = wishlisted ? _t("Remove from wishlist") : _t("Add to wishlist");
    const label = el.querySelector(".o_label");

    if (label) {
        label.textContent = title;
    }

    el.title = title;
}

function paintAll() {
    document.querySelectorAll(BUTTON).forEach((el) => paint(el, isWishlisted(el)));
}

/**
 * Say, visibly, that something happened.
 *
 * ADDING ANIMATED AND REMOVING DID NOT, and the pointer is still ON the heart
 * when the click lands - where the hover rule fills an empty heart red to
 * preview the next add. So a removal left a red heart under the cursor,
 * looking exactly like a click that had not worked. The class drives the
 * shrink and suppresses that preview until the pointer leaves.
 */
function flash(el, className) {
    el.classList.add(className);

    const clear = () => {
        el.classList.remove(className);
        el.removeEventListener("mouseleave", clear);
    };

    el.addEventListener("mouseleave", clear);
    setTimeout(() => el.classList.remove("o_aa_wish_added"), 600);
}

async function onClick(ev) {
    const el = ev.target.closest?.(BUTTON);

    if (!el) {
        return;
    }

    const productId = productOf(el);

    if (!productId) {
        // A button that does not know its variant yet - the product page picks
        // one from the options first. That is Odoo's path and it still works;
        // this one steps aside rather than guessing.
        return;
    }

    ev.preventDefault();
    ev.stopPropagation();

    if (el.dataset.aaBusy) {
        return;
    }

    el.dataset.aaBusy = "1";

    try {
        if (isWishlisted(el)) {
            await rpc("/shop/wishlist/remove_product", { product_id: productId });
            wishlistUtils.removeWishlistProduct(productId);
            paint(el, false);
            flash(el, "o_aa_wish_removed");
        } else {
            await rpc("/shop/wishlist/add", { product_id: productId });
            wishlistUtils.addWishlistProduct(productId);
            paint(el, true);
            flash(el, "o_aa_wish_added");
        }

        wishlistUtils.updateWishlistNavBar();
    } finally {
        delete el.dataset.aaBusy;
    }
}

document.addEventListener("click", onClick, true);

// WHAT THE PAGE KNOWS BEFORE ANYBODY CLICKS. The server marks what it can; the
// ids fill in the rest, and are fetched here if this tab has never asked for
// them - without that, a heart on a page served from a cache sits empty next
// to a wishlist that has the product in it.
async function paintOnArrival() {
    paintAll();

    if (!wishlistUtils.getWishlistProductIds().length) {
        try {
            wishlistUtils.setWishlistProductIds(
                await rpc("/shop/wishlist/get_product_ids")
            );
        } catch {
            return;
        }

        paintAll();
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paintOnArrival);
} else {
    paintOnArrival();
}
