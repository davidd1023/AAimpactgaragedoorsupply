{
    'name': 'AA Dealer Orders',
    'version': '19.0.1.3.1',
    'summary': 'Preferred-dealer ordering on account: Quick Order page and "Charge to Account" checkout',
    'description': """
Lets a preferred dealer (AA Impact Garage Door) order hardware kits without paying
at the moment of ordering.

* "Preferred Dealer - Order on Account" flag on the contact (Sales & Purchase tab).
* A "Charge to Account" payment option that ONLY flagged dealers see at checkout.
  Everyone else keeps seeing Stripe only.
* Orders placed on account are confirmed automatically (work order, MOs, stock).
* /dealer/order - a one-page Quick Order form for dealers: pick the kit series,
  options and quantities for several doors at once, enter the PO number and submit.
    """,
    'author': 'AA Impact Garage Door Supply',
    'category': 'Website/eCommerce',
    'depends': ['website_sale', 'sale_management', 'payment_custom', 'portal', 'spring_engineering'],
    'data': [
        'data.xml',
        'views.xml',
        'templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aa_dealer_orders/static/src/css/dealer_order.css',
            'aa_dealer_orders/static/src/js/spring_bridge.js',
            'aa_dealer_orders/static/src/js/dealer_order.js',
            'aa_dealer_orders/static/src/js/kit_page.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
