{
    'name': 'Spring Engineering',
    # Odoo's convention is <series>.<major>.<minor>.<patch>. It was a bare
    # '1.0', which tells a deployment nothing about which series it belongs to
    # and never changes, so an upgrade had no version to compare against.
    # BUMPED WHENEVER A DATA FILE CHANGES, which is what this number is for.
    # Code on disk - controllers, routes, assets - is live as soon as the
    # workers restart. Records in 'data' only load when the module is UPDATED
    # in that database. Adding product_custom_spring without moving the version
    # left branches where /spring-calculator/add-to-cart answered "the spring
    # product is missing", because the route was there and the record was not.
    # Higher than either side: a JS asset changed, and Odoo.sh rebuilds a
    # bundle only for a module it actually updates.
    #
    # WHEN MERGING, CHECK THIS AGAINST THE BRANCH BEING MERGED INTO, not just
    # against the base. Two branches bumping to the SAME number is a conflict
    # git cannot see - the line is identical, so it merges without a word - and
    # the module then arrives on a database already holding that number, with
    # nothing to compare against. Nothing is upgraded: new data files never
    # load, and a field declared in Python has no column behind it. That is
    # exactly how main and Prod both reached 19.0.2.28.0 carrying different
    # code. Every number since is deliberately ahead of what Prod holds.
    'version': '19.0.2.57.0',
    'category': 'Engineering',
    'summary': 'Spring engineering calculator',
    # Odoo warns on every registry load without this.
    'author': 'AA Impact Garage Door Supply',
    'depends': [
        'sale_management', 'base', 'web', 'website', 'website_sale',
        # The wishlist heart on a product card is turned into a toggle, which
        # patches that module's own interaction - so it has to be there.
        'website_sale_wishlist',
        # The signup form and its controller are extended: a real address,
        # and a link that proves it.
        'auth_signup'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template_confirm_email.xml',
        'data/track_prep_data.xml',
        'data/website_wishlist_data.xml',
        'data/trim_data.xml',
        'data/variant_attributes_data.xml',
        'views/variant_merge_views.xml',
        'views/spring_engineering_views.xml',
        'views/spring_engineering_templates.xml',
        'views/custom_torsion_spring_templates.xml',
        'views/spring_engineering_product.xml',
        'views/wishlist_templates.xml',
        'views/reorder_templates.xml',
        'views/cart_included_parts.xml',
        'views/cart_cost.xml',
        'views/minimum_order.xml',
        'views/quantity_limits.xml',
        'views/signup_templates.xml',
        'views/spring_engineering_settings.xml',
        'views/spring_engineering_config_settings.xml',
    ],
    # The SAME three files in both bundles. The backend app and the public
    # website page run one component from one source; there is no second copy
    # to drift.
    'assets': {
        'web.assets_backend': [
            'spring_engineering/static/src/js/spring_engineering.js',
            'spring_engineering/static/src/xml/spring_engineering.xml',
            'spring_engineering/static/src/css/spring_engineering.css',
        ],
        'web.assets_frontend': [
            'spring_engineering/static/src/js/spring_engineering.js',
            'spring_engineering/static/src/xml/spring_engineering.xml',
            'spring_engineering/static/src/css/spring_engineering.css',
            'spring_engineering/static/src/css/spring_engineering_site.css',
            # The wishlist heart, turned from a stamp into a switch.
            'spring_engineering/static/src/js/wishlist_toggle.js',
            'spring_engineering/static/src/css/wishlist_toggle.css',
            # Reordering a whole previous order from the cart.
            'spring_engineering/static/src/js/reorder_orders.js',
            'spring_engineering/static/src/js/reorder_panel.js',
            'spring_engineering/static/src/css/cart_included.css',
            # A quantity box that holds only quantities.
            'spring_engineering/static/src/js/quantity_limits.js',
            # Says a bad address is bad while the customer is still looking
            # at the box, rather than after they press Sign up.
            'spring_engineering/static/src/js/signup_email_check.js',
        ],
        'web.assets_tests': [
            'spring_engineering/static/tests/tours/wishlist_toggle_tour.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
