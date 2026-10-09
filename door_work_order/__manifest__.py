{
    'name': "Garage Door Work Orders",
    'version': '19.0.1.0.0',
    'summary': "Turn a door calculator result into a manufacturing order",
    'description': """
Takes the tracks and cables worked out by the shop's own door calculator and
raises ONE manufacturing order per door, carrying the cut list.

It is deliberately a module of its own rather than part of spring_engineering.
spring_engineering is a WEBSITE module - it serves the public spring calculator
and the shop pages - and making it depend on mrp would force Manufacturing to be
installed anywhere the spring calculator is wanted. These two features share a
source of numbers and nothing else.
""",
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': ['mrp'],
    'data': [
        'security/ir.model.access.csv',
        'data/door_work_order_data.xml',
        'views/door_work_order_templates.xml',
        'views/mrp_production_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
