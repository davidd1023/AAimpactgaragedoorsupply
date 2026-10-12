{
    'name': "Work Order Sheet",
    'version': '19.0.1.12.0',
    'summary': "Print what a work order is for, product by product",
    'description': """
Adds a printable sheet to a work order - the transfer the shop sees under
Operations > Work Orders (Pedidos) - listing every product on it, with the
length read out of the name for the ones that have one.

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
        'report/work_order_sheet_reports.xml',
    ],
    'installable': True,
    'application': False,
}
