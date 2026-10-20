{
    'name': 'AA Dealer Orders',
    'version': '19.0.1.7.3',
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
    # NEVER DEPEND ON garage_door_supply FROM HERE, and this is the whole
    # reason the line is commented at all.
    #
    # The tax-exempt registration applies a fiscal position that
    # garage_door_supply ships, and declaring that as a dependency looked
    # tidy. garage_door_supply ALSO owns the front page: aa_impact_homepage
    # inherits website.homepage and REPLACES the whole of //div[@id='wrap'].
    # Putting it in this module's dependency graph is enough for an update of
    # this module to carry it along, and re-applying that view puts the
    # shipped hero back over whatever has been done to the page in the website
    # builder. The owner restored a backup on 2026-10-19 and watched the page
    # change back, which is what proved it.
    #
    # The position is found with env.ref(..., raise_if_not_found=False)
    # instead, which needs no dependency and already says something useful
    # when it is missing. `account` is not declared either: it arrives through
    # sale -> account_payment -> account, so naming it here would add another
    # edge for nothing.
    'depends': ['website_sale', 'sale_management', 'payment_custom', 'portal',
                'spring_engineering'],
    'data': [
        'data.xml',
        'resale_data.xml',
        'custom_kit_data.xml',
        'views.xml',
        'resale_views.xml',
        'templates.xml',
        'resale_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aa_dealer_orders/static/src/css/dealer_order.css',
            'aa_dealer_orders/static/src/js/spring_bridge.js',
            'aa_dealer_orders/static/src/js/dealer_order.js',
            'aa_dealer_orders/static/src/js/kit_page.js',
            'aa_dealer_orders/static/src/js/custom_kit.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
