{
    'name': 'AA Order Coverage',
    'version': '19.0.1.12.0',
    'summary': 'Which open orders the stock on hand can complete, first come first served',
    'description': """
Owner, 2026-11-18: "necesito hacer algo en inventario que cuando entre me
salgan todas las ordenes, una vez que entre debo ver hasta cual me da con el
inventario que tengo actualmente para completarlas, y ademas debo tener
filtros por los articulos que llevan las ordenes, por ejemplo quiero saber
solamente de los tracks hasta que orden me llega o las bisagras."

* Inventory > Reporting > Order Coverage: every open Work Order, in the order
  it came in, with every part it still needs.
* The stock on hand is handed out FIRST COME FIRST SERVED: the oldest order
  takes what it needs, the next one gets what is left, and so on. Each line
  says how much was left when its turn came and how much it is short.
* The family panel on the left (Tracks, Hinges, Rollers...) narrows it to the
  parts you care about, so "how far do my tracks go" is one click.
* Coverage by Family answers the question directly: for each family, how
  many orders in a row are covered and which is the first one that is not.

The figures are worked out fresh every time the menu is opened.
""",
    'author': 'AA Impact Garage Door Supply',
    'category': 'Inventory/Inventory',
    'depends': ['stock', 'mrp', 'sale_stock', 'purchase_stock'],
    'data': [
        'security/ir.model.access.csv',
        'security/coverage_rules.xml',
        'data/families.xml',
        'views/coverage_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'aa_order_coverage/static/src/board/*',
        ],
    },
    # SHOWN IN THE APPS LIST: a module that is not an application is hidden
    # by the Apps screen's default filter, and merging a branch never
    # installs a new module (see aa_min_max).
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
