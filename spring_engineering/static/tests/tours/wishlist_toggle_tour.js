/** @odoo-module **/

import { registry } from "@web/core/registry";

// WHAT THE OWNER ASKED FOR, DRIVEN IN A REAL BROWSER.
//
// Both claims are about what happens between page loads and on a second
// click, which no server-side test can see: the heart has to stay red after
// leaving the page and coming back, and clicking it red has to take the
// product off the list.
registry.category("web_tour.tours").add("aa_wishlist_toggle", {
    url: "/shop?search=Heart+Probe+Roller",
    steps: () => [
        {
            content: "the heart starts empty",
            trigger: ".oe_product_cart .o_add_wishlist:not(.o_in_wishlist)",
            run: "click",
        },
        {
            content: "it fills, and the navbar counts it",
            trigger: ".oe_product_cart .o_add_wishlist.o_in_wishlist",
        },
        {
            content: "the count is 1",
            trigger: ".my_wish_quantity:contains(1)",
        },
        {
            content: "leave the page and come back",
            trigger: "body",
            run() {
                window.location.href = "/shop?search=Heart+Probe+Roller";
            },
        },
        {
            content: "THE POINT: it is still red on a fresh page",
            trigger: ".oe_product_cart .o_add_wishlist.o_in_wishlist",
            run: "click",
        },
        {
            content: "clicking it red takes the product off the list",
            trigger: ".oe_product_cart .o_add_wishlist:not(.o_in_wishlist)",
        },
        {
            content: "and the count goes back to nothing",
            trigger: ".my_wish_quantity:contains(0)",
        },
    ],
});
