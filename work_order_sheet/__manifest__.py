{
    'name': "Work Order Sheet",
    'version': '19.0.1.18.0',
    'summary': "Print a work order, and sort its work onto the benches",
    'description': """
Adds a printable sheet to a work order - the transfer the shop sees under
Operations > Work Orders (Pedidos) - listing every product on it, with the
length read out of the name for the ones that have one.

WORK STATIONS. The same rule that splits the sheet into pages - Tracks,
Springs, Cables and Hardware - also sorts the work onto three benches when a
transfer is confirmed. Each bench has a kiosk link of its own showing only its
own queue, with the cut lengths and the door it is building for, and a Done
button. Hardware is not a station: those parts come off a shelf against the
transfer.

SEPARATE FROM door_work_order ON PURPOSE. That module exists to receive a door
from the external calculator and raise a manufacturing order; this one prints
what a customer ordered on the website. They share a look and nothing else, and
this one depends on stock rather than mrp so it carries no manufacturing
machinery it does not use.
""",
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'report/work_order_sheet_reports.xml',
        'views/station_templates.xml',
        'views/work_station_views.xml',
        'data/work_station_data.xml',
    ],
    'installable': True,
    'application': False,
}
