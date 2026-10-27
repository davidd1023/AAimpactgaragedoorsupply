# -*- coding: utf-8 -*-
{
    "name": "AA Pickup Slots",
    "version": "19.0.2.0.0",
    "summary": "A pickup day and time window chosen at checkout, carried to the floor",
    "description": """
WHEN THE CUSTOMER IS COMING TO COLLECT.

Owner, 2026-10-27: "At checkout, the customer picks a pickup day and time
window, and it shows on the Work Order and in Dispatch. Done when: the chosen
slot appears on the order and the Dispatch list. (Our lead time is 2 labor
days, after those 2 days they choose when to pick up)."

Three answers he gave when asked:

  * THE LEAD TIME STARTS THE NEXT WORKING DAY and takes two whole ones, so an
    order placed Monday is collectable from THURSDAY, and one placed Friday
    from Wednesday.
  * TWO-HOUR WINDOWS - 8-10, 10-12, 12-2, 2-4:30 - which are tight enough to
    plan the counter around and wide enough that nobody is late by ten
    minutes.
  * PICKUP ORDERS ONLY, AND REQUIRED. Anything being delivered is never
    asked; anything being collected cannot be paid for without a slot, so
    nothing reaches Dispatch blank for somebody to chase by telephone.
""",
    "category": "Website/Website",
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
    "depends": ["website_sale", "work_order_sheet"],
    "data": [
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        "views/res_config_settings_views.xml",
        "views/checkout_templates.xml",
        "report/work_order_sheet.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "aa_pickup_slots/static/src/scss/pickup_slot.scss",
            "aa_pickup_slots/static/src/js/pickup_slot.js",
        ],
    },
    "post_init_hook": "_aa_mark_pickup_carriers",
    "installable": True,
    "application": False,
    "auto_install": False,
}
