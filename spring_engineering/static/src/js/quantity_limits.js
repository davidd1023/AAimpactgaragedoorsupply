/** @odoo-module **/

// A QUANTITY BOX THAT HOLDS ONLY QUANTITIES.
//
// The server decides what a cart may hold - see _aa_bounded_quantity, which
// is the only thing that can, because anybody can post to the route without
// ever loading this page. This is the courtesy in front of it: the customer
// meets the rule while typing instead of after pressing Add, and the number
// Odoo reads out of the box is a number.
//
// LISTENING ON THE DOCUMENT, IN THE CAPTURE PHASE, for the same reason the
// wishlist does: Odoo binds its own "change" handler to the input itself, and
// the cart replaces these inputs whenever a line is updated. A capture
// listener on the document runs before the handler on the box, whoever bound
// it and whenever, and there is nothing to re-bind when the cart redraws.
//
// It does NOT stop the event. Odoo's handler is meant to run - it is what
// sends the new quantity - it should just be reading a sane value by then.
const BOXES = 'input[name="add_qty"], input.js_quantity';

function boundsOf(el) {
    const min = parseInt(el.getAttribute("min"));
    const max = parseInt(el.getAttribute("max"));

    return {
        min: Number.isFinite(min) ? min : 1,
        // No max attribute means the shop set no limit. The server still has
        // the last word; this simply has nothing to enforce.
        max: Number.isFinite(max) ? max : Infinity,
    };
}

/**
 * Keep the keystrokes to digits, WITHOUT correcting the number yet.
 *
 * Clamping while somebody is still typing is its own small cruelty: a max of
 * 10 would rewrite "12" to "10" between the 1 and the 2, and the customer
 * would be fighting the box. Anything that is not a digit is dropped, an
 * empty box is left empty, and the value is put right when they leave.
 */
function onInput(ev) {
    const el = ev.target;

    if (!el.matches?.(BOXES)) {
        return;
    }

    const digits = String(el.value).replace(/[^0-9]/g, "");

    if (digits !== el.value) {
        el.value = digits;
    }
}

/**
 * Put the number right before Odoo reads it.
 *
 * An empty box, or one holding something that is not a number at all, means
 * the smallest the shop will sell rather than zero: zero on the cart page is
 * how a line is REMOVED, and somebody who typed a word did not ask for that.
 */
function onChange(ev) {
    const el = ev.target;

    if (!el.matches?.(BOXES)) {
        return;
    }

    const { min, max } = boundsOf(el);
    const asked = parseInt(String(el.value).replace(/[^0-9-]/g, ""), 10);
    const settled = Number.isFinite(asked)
        ? Math.min(Math.max(asked, min), max)
        : min;

    if (String(settled) !== el.value) {
        el.value = settled;
    }
}

document.addEventListener("input", onInput, true);
document.addEventListener("change", onChange, true);
