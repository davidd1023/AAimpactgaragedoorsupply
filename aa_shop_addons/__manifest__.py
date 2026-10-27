# -*- coding: utf-8 -*-
{
    "name": "AA Shop Add-ons",
    "version": "19.0.2.2.0",
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

THEN HE ASKED FOR IT WITHOUT THE TYPING (2026-10-27): "could you automate a
system that will recommend additional products the same way that the
alternative product thing works. this way i wont have to individually go into
every products page to seach which products i should recommend alongside it."

He had already answered the question himself, at the counter, all year. A kit
still does not know the door height - but "which cable do people who buy this
kit buy" is a COUNTING question, and the answer is in his order book. So the
pairs are counted out of sale_order_line every night, and a product is
recommended once enough real orders have carried both. Nothing is guessed:
everything it says, his own shop has done.

Three tiers, in order: what HE picked, then what his ORDERS say, then the
families - so a page is never blank and his own pick is never overruled.

NOT IN garage_door_supply, deliberately. That module owns the homepage view
and every update of it puts the shipped hero back over the website builder.
""",
    "category": "Website/Website",
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
    "depends": ["website_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/addon_suggestion_cron.xml",
        "views/addon_suggestion_views.xml",
        "views/res_config_settings_views.xml",
        "views/product_views.xml",
        "views/product_addons_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
