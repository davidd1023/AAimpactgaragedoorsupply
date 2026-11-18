{
    'name': 'AA Part Numbers',
    'version': '19.0.1.1.0',
    'summary': "AA Impact's own part number on every stocked product",
    'description': """
Owner, 2026-11-18: "quiero ponerle nuestro part number a todos nuestros
productos" - created and assigned here, a prefix per family (AA-TRK-001),
the variants of a product sharing the number with a letter at the end to
tell them apart, and only on the products that are kept in stock.

* AA Part # sits beside the supplier's Internal Reference, which is left
  exactly as it is.
* Every stocked product is numbered on install, and every new one as it is
  created. A number, once given, never changes.
* Search any product list by AA part number.
""",
    'author': 'AA Impact Garage Door Supply',
    'category': 'Inventory/Inventory',
    'depends': ['product', 'stock'],
    'data': [
        'views/part_number_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    # Shown in Apps, which filters to applications by default: a new module
    # is never installed by a merge (see aa_min_max).
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
