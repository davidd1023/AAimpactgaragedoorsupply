# -*- coding: utf-8 -*-
{
    "name": "AA Shop Add-ons",
    "version": "19.0.1.0.0",
    "summary": "Cones, cables, tracks and trims shown under a kit or a spring",
    "description": """
THE EXTRAS A CUSTOMER STILL NEEDS, UNDER THE THING THEY ARE LOOKING AT.

Owner, 2026-10-27: "On every kit and spring page, show the matching add-ons
(cones, cables, tracks, trims) below the product. Done when: each kit shows
its correct add-ons."

WHAT MAKES ONE "CORRECT" IS HIS CALL, NOT A RULE. A kit knows its series and
its panel count and nothing else - not the door height, the colour or the
track size, which are the things that actually pick one cable or one track
out of twenty. Asked, he chose to set them himself: Odoo's own Alternative
Products field on each of the twelve kits, which is right by definition
because he says so. Odoo's help for that field says the products "show up on
the product page", which is where he asked for these - and the other two
boxes in that group are hidden, so there is one place to fill in rather than
three that look alike.

The families are the fallback, so a product nobody has got to yet still shows
the right kinds rather than an empty space.

NOT IN garage_door_supply, deliberately. That module owns the homepage view
and every update of it puts the shipped hero back over the website builder.
""",
    "category": "Website/Website",
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
    "depends": ["website_sale"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/product_views.xml",
        "views/product_addons_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
