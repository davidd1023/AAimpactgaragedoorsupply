{
    'name': 'Spring Engineering',
    'version': '1.0',
    'category': 'Engineering',
    'summary': 'Spring engineering calculator',
    'depends': ['base', 'web'],
    'data': [
        'views/spring_engineering_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'spring_engineering/static/src/js/spring_engineering.js',
            'spring_engineering/static/src/xml/spring_engineering.xml',
            'spring_engineering/static/src/css/spring_engineering.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}