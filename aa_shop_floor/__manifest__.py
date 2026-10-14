{
    'name': 'AA Shop Floor',
    'version': '19.0.1.2.0',
    'summary': 'Each Shop Floor station shows exactly what to make for the order',
    'description': """
The Shop Floor card tells the worker what to make, without opening anything else.

* Springs: a custom spring from Spring Engineering (the calculator, the Custom
  Torsion Spring page or the dealer Quick Order) becomes a manufacturing order at
  the Springs station when the sale is confirmed. Its card shows the assembly
  (Single / Duplex), wire, I.D., length, and how many LH and RH.
* Finished stock springs (SPR-<wire>-<ID>-<L/R>) show wire, I.D. and hand.

Spring specs only ever appear on Springs work orders. Hardware gets its own
block later, with only its own parts (kit, drum, lift cable).
""",
    'author': 'AA Impact Garage Door Supply',
    'category': 'Manufacturing',
    'depends': ['mrp_workorder', 'sale', 'spring_engineering'],
    'data': [
        'data/aa_shop_floor_data.xml',
        'views/mrp_production_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'aa_shop_floor/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
