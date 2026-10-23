{
    'name': 'AA Shop Floor',
    'version': '19.0.1.29.0',
    'summary': 'Each Shop Floor station shows exactly what to make for the order',
    'description': """
The Shop Floor card tells the worker what to make, without opening anything else.

* Springs: a custom spring from Spring Engineering (the calculator, the Custom
  Torsion Spring page or the dealer Quick Order) becomes a manufacturing order at
  the Springs station when the sale is confirmed. Its card shows the assembly
  (Single / Duplex), wire, I.D., length, and how many LH and RH.
* Finished stock springs (SPR-<wire>-<ID>-<L/R>) show wire, I.D. and hand.

Spring specs only ever appear on Springs work orders. The Hardware card lists
only what goes in the box (kit, its pieces, lift cables).

* What for: a button beside Start on the Hardware page opens the door that box
  is for - the spring and its turns, the drum the figures were worked out on,
  the finish, the lift, the cable and the track lengths - and prints a 4 x 6
  sticker for the box. The sticker's QR code opens the same list on a phone,
  with no login: the link is the key. One door per card on a multi-door order,
  and a fact the order never stated is left out rather than guessed at.
""",
    'author': 'AA Impact Garage Door Supply',
    'category': 'Manufacturing',
    # sale_mrp puts the order's manufacturing ORDER NUMBERS on the customer's
    # portal page; the station progress replaces them, so it has to be there to
    # be replaced. It installs itself anyway wherever sale and mrp both are.
    'depends': ['mrp_workorder', 'sale', 'sale_mrp', 'spring_engineering', 'work_order_sheet'],
    'data': [
        'security/ir.model.access.csv',
        'views/orphan_cleanup_views.xml',
        'data/aa_shop_floor_data.xml',
        'data/aa_pending_workcenter.xml',
        'views/mrp_production_views.xml',
        'views/hardware_box_templates.xml',
        'views/portal_templates.xml',
        'views/res_config_settings_views.xml',
        'report/hardware_sticker.xml',
        'views/aa_shop_floor_history_views.xml',
        'data/aa_shop_floor_action.xml',
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
