# -*- coding: utf-8 -*-
{
    "name": "AA Door Preview",
    "version": "19.0.1.0.0",
    "summary": "The Series 1200 3D preview: one model, the colours swapped live",
    "description": """
THE DOOR PREVIEW, KEPT IN THE REPOSITORY EVEN THOUGH IT SHIPS TO WORDPRESS.

aaimpactgaragedoor.com is WordPress on HostGator and its product pages carry a
Sirv 3D viewer. The replacement is an ordinary self-contained bundle - one JS
file, one CSS file, a texture and three.js - and none of it needs Odoo to run.

It lives here anyway, for two reasons: this container is ephemeral and
anything not committed is lost on a rebuild, and Odoo will serve the test page
over HTTP so the thing can be looked at on a real origin before it is put
anywhere near the live site.

    /aa_door_preview/static/src/preview.html

NO MODELS, NO VIEWS, NO DATA. Installing it changes nothing in the database;
the module exists so the addons path will serve the folder.
""",
    "category": "Website",
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
