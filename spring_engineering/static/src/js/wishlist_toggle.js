/** @odoo-module **/

import { _t, translationIsReady } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

import wSaleUtils from "@website_sale/js/website_sale_utils";
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

// TWO BUTTONS, AND THE DIFFERENCE BETWEEN THEM MATTERS.
//
//   a shop card (.o_add_wishlist)      one heart for a whole template, which
//                                      offers the first variant it can find
//   a product page (.o_add_wishlist_dyn)  one button for the ONE variant the
//                                      options currently select
//
// Odoo's interaction covers both, so leaving the second one out left it in
// Odoo's hands: it added, disabled itself, and the customer could not press it
// again to take the product off. Worse, a disabled .btn is pointer-events:
// none, so the second click raised no event at all - there was nothing for
// this file to intercept even if it had been listening.
//
// AND ONE THAT ONLY LOOKS LIKE THE FIRST. The cart's "Save for Later" link
// carries o_add_wishlist too, with a real variant id - but it is not a toggle:
// it puts the product on the list AND takes the line out of the cart, and that
// second half is bound on an ancestor, so stopping the click here stopped it
// as well. It saved the product and left it in the cart. Odoo's own handlers
// do that one properly between them, so it is left alone.
const CARD = ".o_add_wishlist:not(.js_delete_product)";
const DYN = ".o_add_wishlist_dyn";
const BUTTON = `${CARD}, ${DYN}`;

// Which variant of each template is the one on the list. Odoo keeps the ids in
// the session and that is not enough on its own - see /shop/wishlist/state.
const MAP_KEY = "aa_wishlist_variants";

function productOf(el) {
    return parseInt(el.dataset.productProductId) || 0;
}

function templateOf(el) {
    return parseInt(el.dataset.productTemplateId) || 0;
}

function variantMap() {
    try {
        return JSON.parse(sessionStorage.getItem(MAP_KEY) || "{}");
    } catch {
        return {};
    }
}

function rememberVariant(templateId, productId, wishlisted) {
    if (!templateId) {
        return;
    }

    const map = variantMap();

    if (wishlisted) {
        map[templateId] = productId;
    } else {
        delete map[templateId];
    }

    try {
        sessionStorage.setItem(MAP_KEY, JSON.stringify(map));
    } catch {
        // A browser refusing storage still gets working hearts on the page it
        // is looking at; only the memory of them across pages is lost.
    }
}

/**
 * What the page itself says, as the server drew it.
 *
 * Read BEFORE painting, because painting clears the very attribute this looks
 * at. The card says it with a class; the product page button says it by being
 * disabled, which is also how Odoo colours that one in.
 */
function serverSaysWishlisted(el) {
    return el.classList.contains("o_in_wishlist")
        || el.classList.contains("disabled")
        || el.hasAttribute("disabled");
}

/**
 * The variant this button could take off the list, or 0 if there is none.
 *
 * A CARD STANDS FOR THE TEMPLATE, A PRODUCT PAGE FOR ONE VARIANT. So the card
 * may answer with a variant that is not the one it offers - that is the whole
 * point of the mapping, and it is what was wrong when a product wishlisted
 * from its own page left the shop card looking untouched: the card held the
 * first variant, the list held the one that was chosen, and the two numbers
 * were never going to match.
 *
 * The product page gets no such latitude. It is showing one variant and must
 * tell the truth about that one, or the button would offer to remove a row
 * the customer is not looking at.
 */
function wishlistedVariant(el) {
    const ids = wishlistUtils.getWishlistProductIds();
    const own = productOf(el);

    if (own && ids.includes(own)) {
        return own;
    }

    if (el.matches(DYN)) {
        return 0;
    }

    const mapped = parseInt(variantMap()[templateOf(el)]) || 0;

    return mapped && ids.includes(mapped) ? mapped : 0;
}

function isWishlisted(el) {
    // TWO OPINIONS, EITHER OF WHICH IS ENOUGH. The browser's list answers
    // first; the page's own markup answers for a tab that has never asked the
    // server for the list, and for a card drawn somewhere the shop page's
    // variant mapping does not reach.
    //
    // THE MARKUP IS BELIEVED ABOUT THE PRODUCT, NOT ABOUT THE VARIANT. Odoo
    // marks a card from the template - any variant on the list reddens it -
    // so its id cannot be taken as the row's id, and writing it into the
    // browser's list would plant a number that is wrong and sticks. Which
    // variant it really is comes from the server, in the one fetch below, or
    // is left to the server to work out when the heart is pressed.
    return Boolean(wishlistedVariant(el)) || serverSaysWishlisted(el);
}

function paint(el, wishlisted) {
    el.classList.toggle("o_in_wishlist", wishlisted);

    // NEVER DISABLED. Odoo disables the button once the product is on the list
    // - which is also how it colours it red - and a disabled button swallows
    // the very click that would take the product off again. The ATTRIBUTE has
    // to go as well as the property: the product page button is an <a>, where
    // setting .disabled is a property no browser acts on and the attribute the
    // server wrote would have stayed behind.
    el.disabled = false;
    el.classList.remove("disabled");
    el.removeAttribute("disabled");

    const icon = el.querySelector(".fa");

    if (icon) {
        icon.classList.toggle("fa-heart", wishlisted);
        icon.classList.toggle("fa-heart-o", !wishlisted);
    }

    // THE WORDS COME LAST, AND MAY NOT TAKE THE COLOUR WITH THEM.
    //
    // _t DOES NOT RETURN A STRING. It returns a lazy TranslatedString which
    // THROWS the moment it is turned into one, if the translation file has not
    // arrived yet:
    //
    //     throw new Error(`Cannot translate string: translations have not
    //                      been loaded`)                 - translation.js:168
    //
    // and it is turned into one by the assignments below, not by _t itself.
    // This function runs from paintOnArrival, on DOMContentLoaded, which is
    // sometimes earlier than the translations - and once a second language was
    // installed on the site, regularly earlier. The throw landed in the MIDDLE
    // of painting, so the heart lost its colour as well as its tooltip, every
    // page logged an uncaught error, and the hearts "went back to default" at
    // random - which is the intermittent half of the wishlist bug.
    //
    // So the state is painted first and the words are attempted after, where
    // failing to translate costs only a tooltip. paintOnArrival paints again
    // as soon as the translations land.
    try {
        const title = wishlisted
            ? _t("Remove from wishlist")
            : _t("Add to wishlist");
        // The card labels its text .o_label; the product page just puts a span
        // after the icon. The icon itself is the only other span on the card,
        // so skipping it finds the words on both.
        const label = el.querySelector(".o_label")
            || el.querySelector("span:not(.fa)");

        if (label) {
            label.textContent = title;
        }

        if (icon && icon.hasAttribute("aria-label")) {
            icon.setAttribute("aria-label", title);
        }

        el.title = title;
    } catch {
        // Painted again from paintOnArrival once the translations exist. The
        // heart is already the right colour, which is the part that matters.
    }
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

/**
 * The variant to put on the list when the button is pressed.
 *
 * A product sold with dynamic options has no variant until somebody asks for
 * one, which is why the button can carry no id at all. Odoo creates it from
 * the options on screen; so does this, by the same route.
 */
async function variantToAdd(el) {
    const own = productOf(el);

    if (own) {
        return own;
    }

    const form = wSaleUtils.getClosestProductForm(el);
    const templateId = templateOf(el);

    if (!form || !templateId) {
        return 0;
    }

    return parseInt(await rpc("/sale/create_product_variant", {
        product_template_id: templateId,
        product_template_attribute_value_ids:
            wSaleUtils.getSelectedAttributeValues(form),
    })) || 0;
}

/**
 * What to ask the server to take off the list.
 *
 * A CARD IS ONE HEART FOR A WHOLE TEMPLATE, so it is allowed to say "whichever
 * variant of this product is on the list" - and it has to be, because a card
 * drawn outside the shop page (a product snippet on the home page, say) is
 * marked as wishlisted by Odoo while still offering the FIRST variant's id.
 * Asking by that id alone would find no row, the heart would go quiet, and the
 * product would still be on the list.
 *
 * A product page says nothing of the sort: it is showing one variant, and the
 * row it offers to remove is that variant's or none.
 */
function removalTarget(el, productId) {
    const target = { product_id: productId };

    if (!el.matches(DYN)) {
        target.product_tmpl_id = templateOf(el);
    }

    return target;
}

async function onClick(ev) {
    const el = ev.target.closest?.(BUTTON);

    if (!el) {
        return;
    }

    // STEP ASIDE BEFORE STOPPING THE CLICK, not after. Everything below is
    // asynchronous, and by the time an await comes back the click has long
    // since finished travelling - so the decision to let Odoo's own handler
    // have it has to be made here, synchronously, or not at all. A button with
    // neither a variant nor a form to work one out from is Odoo's problem.
    if (!productOf(el) && !wSaleUtils.getClosestProductForm(el)) {
        return;
    }

    ev.preventDefault();
    ev.stopPropagation();

    if (el.dataset.aaBusy) {
        return;
    }

    el.dataset.aaBusy = "1";

    try {
        const onTheList = wishlistedVariant(el);

        if (onTheList) {
            await rpc("/shop/wishlist/remove_product", removalTarget(el, onTheList));
            wishlistUtils.removeWishlistProduct(onTheList);
            rememberVariant(templateOf(el), onTheList, false);
            paint(el, false);
            flash(el, "o_aa_wish_removed");
        } else {
            const productId = await variantToAdd(el);

            if (!productId) {
                return;
            }

            await rpc("/shop/wishlist/add", { product_id: productId });
            wishlistUtils.addWishlistProduct(productId);
            rememberVariant(templateOf(el), productId, true);
            // So a second press on THIS button knows what it just added, even
            // on a card that was offering a different variant a moment ago.
            el.dataset.productProductId = productId;
            paint(el, true);
            flash(el, "o_aa_wish_added");
        }

        wishlistUtils.updateWishlistNavBar();
    } finally {
        delete el.dataset.aaBusy;
    }
}

document.addEventListener("click", onClick, true);

// CHOOSING A DIFFERENT OPTION CHOOSES A DIFFERENT PRODUCT. The wishlist is per
// variant, so the heart on a product page has to follow the options: Odoo's
// own handler writes the new variant id onto the button, and this - listening
// where the event bubbles up, which is after that - repaints from it. Without
// this the button would also keep the "disabled" class Odoo puts back on, and
// be unclickable again.
document.addEventListener("change", (ev) => {
    if (ev.target?.matches?.("input.product_id, input[name='product_id']")) {
        paintAll();
    }
});

// WHAT THE PAGE KNOWS BEFORE ANYBODY CLICKS. The server marks what it can; the
// ids fill in the rest, and are fetched here if this tab has never asked for
// them - without that, a heart on a page served from a cache sits empty next
// to a wishlist that has the product in it.
/**
 * How many things the SERVER says are on the list, or null if it did not say.
 *
 * The navbar badge is rendered server-side from the real wishlist, so the
 * answer is already on the page. Reading it is what lets the fetch below be
 * skipped for the overwhelming majority of visits - a visitor with an empty
 * wishlist has nothing to fetch, and asking anyway cost an extra request on
 * every page view of the whole site.
 */
function serverWishlistCount() {
    const badge = document.querySelector(".my_wish_quantity");
    const said = parseInt((badge?.textContent || "").trim(), 10);

    return Number.isFinite(said) ? said : null;
}

async function paintOnArrival() {
    paintAll();

    const onTheList = serverWishlistCount();

    if (onTheList === 0) {
        // Nothing to ask about. Said explicitly so a stale list from an
        // earlier page in this tab is cleared rather than believed.
        wishlistUtils.setWishlistProductIds([]);
    } else if (!wishlistUtils.getWishlistProductIds().length) {
        try {
            const state = await rpc("/shop/wishlist/state");

            wishlistUtils.setWishlistProductIds(state.ids || []);

            try {
                sessionStorage.setItem(
                    MAP_KEY, JSON.stringify(state.variants || {}));
            } catch {
                // see rememberVariant
            }
        } catch {
            // The hearts the server marked are already painted; nothing else
            // can be known without the server, so stop asking.
        }

        paintAll();
    }

    // AND AGAIN WHEN THE WORDS EXIST. The first pass above gets the colour
    // right, which is what a customer reads; the tooltip and the label come
    // from _t, which refuses to be read before the translation file lands.
    // This is the only paint that can be sure of them.
    await translationIsReady;

    paintAll();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paintOnArrival);
} else {
    paintOnArrival();
}

// A PAGE COMING BACK FROM THE BROWSER'S CACHE RUNS NO SCRIPT. Pressing Back
// after wishlisting something restores the shop exactly as it was drawn before
// the add, hearts and all. Nothing above fires for that, which is the other
// half of "sometimes it doesn't show": repainting here reads the list this tab
// has kept and puts the hearts right.
window.addEventListener("pageshow", (ev) => {
    if (ev.persisted) {
        paintAll();
    }
});
