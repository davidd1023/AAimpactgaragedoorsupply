{
    'name': 'Spring Engineering',
    'version': '1.0',
    'category': 'Engineering',
    'summary': 'Spring engineering calculator',
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