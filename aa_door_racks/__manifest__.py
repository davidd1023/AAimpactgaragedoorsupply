{
    "name": "Door Racks",
    "version": "19.0.1.0.0",
    "summary": "Where every finished door sits on the cantilever racks at Medley",
    "category": "Inventory/Inventory",
    "depends": ["stock", "sale_stock", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/racks.xml",
        "views/bundle_views.xml",
        "views/rack_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
        "report/bundle_label.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "aa_door_racks/static/src/rack_board.js",
            "aa_door_racks/static/src/rack_board.xml",
            "aa_door_racks/static/src/rack_board.scss",
        ],
    },
    "application": True,
    "installable": True,
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
}
