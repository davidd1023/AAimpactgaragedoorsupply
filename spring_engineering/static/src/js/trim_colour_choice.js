/**
 * Turn the "Trims" extra on a product page into a COLOUR CHOICE instead of a
 * free-text box.
 *
 * HOW THE EXTRAS ON A PRODUCT PAGE ALREADY WORK. An attribute value flagged
 * "Custom value" (product.template.attribute.value.is_custom) makes Odoo reveal
 * a text input when that value is selected, and the cart reads every
 * `.variant_custom_value` element's `.value` and stores it against the
 * attribute. That is the mechanism behind the extras that "pop open a square" -
 * nothing custom, just that checkbox.
 *
 * So Trims needs no new plumbing. It needs its value flagged "Custom value"
 * like the others, and then its box swapped from a text input, where a customer
 * can type anything, to a <select> of the three colours that exist. The swapped
 * element keeps the SAME class and the SAME
 * data-custom-product-template-attribute-value-id, so the cart, the order line
 * and the back end all keep working untouched - a <select>'s `.value` reads
 * exactly like an input's.
 *
 * WHY AN OBSERVER AND NOT A PATCH. The input is built in JS by
 * VariantMixin.handleCustomValues, which is copied onto the page controller
 * with Object.assign at module load - so a patch applied afterwards would be
 * silently ignored, depending on bundle order. Odoo's own source also says
 * "TODO(loti): temporary hack. VariantMixin will be dropped." An observer
 * watching for the input to appear does not care how it got there, or what
 * replaces the mixin later.
 */

// The attribute values this applies to, and the choices each offers. Keyed by
// the value's own name, matched case-insensitively and ignoring a trailing "s",
// so "Trim" and "Trims" both work.
const CHOICES = {
    trim: ["Black", "Bronze", "White"],
};

const KEY = "customProductTemplateAttributeValueId";

export function choicesFor(name) {
    const key = String(name || "").trim().toLowerCase().replace(/s$/, "");

    return CHOICES[key] || null;
}

/**
 * Odoo sets the input's placeholder to the attribute value's own name, which is
 * the only thing on the element that says WHICH extra it belongs to.
 */
export function swap(input) {
    if (!(input instanceof HTMLInputElement)) {
        return;
    }

    const colours = choicesFor(input.getAttribute("placeholder"));

    if (!colours) {
        return;
    }

    const select = document.createElement("select");

    // Same hooks the cart looks for. Without these the choice is collected but
    // attached to nothing, and the order line comes through blank.
    select.classList.add(
        "variant_custom_value", "custom_value_radio", "form-select", "mt-2"
    );
    select.dataset[KEY] = input.dataset[KEY];

    const blank = document.createElement("option");

    blank.value = "";
    blank.textContent = `Select a ${String(input.getAttribute("placeholder") || "trim")
        .trim().toLowerCase().replace(/s$/, "")} colour`;
    select.appendChild(blank);

    for (const colour of colours) {
        const option = document.createElement("option");

        option.value = colour;
        option.textContent = colour;
        select.appendChild(option);
    }

    // Keep a colour the customer already picked, including the value Odoo
    // restores into the input from previous_custom_value when the page is
    // revisited with the extra still selected.
    const existing = colours.find(
        (c) => c.toLowerCase() === String(input.value || "").trim().toLowerCase()
    );

    if (existing) {
        select.value = existing;
    }

    input.replaceWith(select);
}

export function sweep(root) {
    if (!root || !root.querySelectorAll) {
        return;
    }

    for (const input of root.querySelectorAll("input.variant_custom_value")) {
        swap(input);
    }
}

function watch() {
    // The product form, and the same extras shown inside the optional-products
    // modal, which is added to the body rather than to the form.
    const observer = new MutationObserver((records) => {
        for (const record of records) {
            for (const node of record.addedNodes) {
                if (node.nodeType !== Node.ELEMENT_NODE) {
                    continue;
                }

                if (node.matches && node.matches("input.variant_custom_value")) {
                    swap(node);
                } else {
                    sweep(node);
                }
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
    // Anything already on the page before the observer started.
    sweep(document.body);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch, { once: true });
} else {
    watch();
}
