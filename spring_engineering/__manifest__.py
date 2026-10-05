{
    'name': 'Spring Engineering',
    # Odoo's convention is <series>.<major>.<minor>.<patch>. It was a bare
    # '1.0', which tells a deployment nothing about which series it belongs to
    # and never changes, so an upgrade had no version to compare against.
    'version': '19.0.1.1.0',
    'category': 'Engineering',
    'summary': 'Spring engineering calculator',
    # Odoo warns on every registry load without this.
    'author': 'AA Impact Garage Door Supply',
    'depends': ['base', 'web', 'website'],
    'data': [
        'views/spring_engineering_views.xml',
        'views/spring_engineering_templates.xml',
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
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}