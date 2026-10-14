/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import wSaleUtils from "@website_sale/js/website_sale_utils";

// REMOVING A LINE FROM THE CART SHOULD NOT OPEN A PANEL.
//
// Odoo refreshes the quick reorder panel after every cart change, and when the
// refreshed history comes back empty it does this:
//
//     quickReorderButton.click();
//     quickReorderButton.setAttribute('disabled', 'true');
//
// The click is meant to CLOSE the panel. The button is a Bootstrap toggle, so
// when the panel is already closed - which it is, every time somebody simply
// removes a line - the same click OPENS it, and the disable that follows
// means the button cannot shut it again. That is the owner's report exactly:
// the panel appears on its own, and the button greys out until the cart is
// empty, because an emptier cart is what brings the history back.
//
// The history empties for an ordinary reason, too: Odoo leaves out any
// product that is ALREADY in the cart, so a cart holding the things you
// usually buy has nothing left to suggest.
//
// This replaces that one function: it keeps the refresh, closes the panel only
// when it is open, and leaves the button alive while this shop still has
// something to offer - which it does whenever the customer has ordered before.
const refreshPanel = function (data) {
    const button = document.getElementById("quick_reorder_button");

    if (!button) {
        return;
    }

    document.querySelectorAll(".o_wsale_quick_reorder_line_group").forEach(
        (el) => el.remove()
    );

    const history = (data["website_sale.quick_reorder_history"] || "").trim();
    const body = document.querySelector("#quick_reorder_sidebar .offcanvas-body");

    if (history && body) {
        body.insertAdjacentHTML("afterbegin", history);
    }

    // The orders list is rendered with the page and is not touched by a cart
    // update, so its presence is the test for "there is still something here".
    const hasPreviousOrders = Boolean(
        document.querySelector(".o_aa_reorder_orders")
    );

    if (history || hasPreviousOrders) {
        button.removeAttribute("disabled");
        button.parentElement.title = "";

        return;
    }

    const panel = document.getElementById("quick_reorder_sidebar");

    if (panel && panel.classList.contains("show")) {
        button.click();
    }

    button.setAttribute("disabled", "true");
    button.parentElement.title = _t("No previous products available for reorder.");
};

// Both callers reach it through this object - the cart line interaction and
// the panel's own - so replacing the property is enough.
wSaleUtils.updateQuickReorderSidebar = refreshPanel;
