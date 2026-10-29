{
    'name': 'AA Min / Max Stock Levels',
    'version': '19.0.1.0.0',
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
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
