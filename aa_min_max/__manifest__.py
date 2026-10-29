{
    'name': 'AA Min / Max Stock Levels',
    'version': '19.0.1.3.0',
    'summary': 'A minimum (and maximum) per part, and one screen saying what is below it',
    'description': """
Owner, 2026-10-29: *"make minimum and maximum of each item, same thing we did
for the spring in which we need to make a warning when an item is below its
minimum so that we can make a reorder of that product. I want you to show this
all in a new menu youll make in inventory, in the reporting tab, so that way we
can easily see the max and min of each item."*

* Inventory > Reporting > **Min / Max Levels**: every stockable part with its
  minimum, its maximum, what is on hand, and HOW FAR BELOW it is.
* The levels are kept in ODOO'S OWN REORDERING RULES, not in a field of our
  own, so the reorder he is heading towards is Odoo's Replenishment screen
  rather than anything that has to be built.
* The 157 minimums he filled in are loaded from `data/minmax_levels.csv`,
  matched on part number AND variant name - since the catalogue merge a part
  number belongs to a whole family, so `CH1108` alone cannot tell eight jamb
  brackets apart.
* Nothing is guessed: a row that matches no product, or several, is reported
  on the screen rather than loaded.
""",
    'author': 'AA Impact Garage Door Supply',
    'category': 'Inventory/Inventory',
    'depends': ['stock', 'purchase_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/minmax_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    # INSTALLS ITSELF. Owner, 2026-10-29: *"im not seeing it in reporting"* -
    # with a screenshot of his Prod showing Stock, Locations, Moves History
    # and Moves Analysis, and no Min / Max Levels.
    #
    # MERGING A BRANCH DOES NOT INSTALL A NEW MODULE. Odoo updates what is
    # already installed and leaves anything new sitting in Apps, so every new
    # module so far has quietly needed somebody to go and find it - and the
    # one person who would have to is the one who asked for the screen.
    #
    # `auto_install` means "install me as soon as everything I depend on is
    # installed" - but that is decided in `odoo/modules/db.py::initialize()`,
    # which the loader calls ONLY when the database is not yet initialised.
    # So it fires on a FRESH database (every new dev build) and NEVER
    # retro-installs on a live one. Checked by uninstalling it here and
    # running both `-u aa_spring_stock` and `-u base`: neither brought it
    # back. Kept because it is right for new builds; it is not the fix.
    'auto_install': True,
    # SHOWN IN THE APPS LIST, which is the fix. Odoo's Apps screen filters to
    # applications by default, so a module with `application: False` is
    # invisible there unless somebody knows to clear a filter - and the one
    # person who would have to is the one who asked for the screen and went
    # looking for it under Reporting.
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
