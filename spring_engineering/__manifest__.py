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
    'version': '19.0.1.6.0',
    'category': 'Engineering',
    'summary': 'Spring engineering calculator',
    # Odoo warns on every registry load without this.
    'author': 'AA Impact Garage Door Supply',
    'depends': [
        'sale_management','base', 'web', 'website', 'website_sale'],
    'data': [
        'data/track_prep_data.xml',
        'views/spring_engineering_views.xml',
        'views/spring_engineering_templates.xml',
        'views/spring_engineering_product.xml',
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
            'spring_engineering/static/src/js/trim_colour_choice.js',
            'spring_engineering/static/src/js/spring_engineering.js',
            'spring_engineering/static/src/xml/spring_engineering.xml',
            'spring_engineering/static/src/css/spring_engineering.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}