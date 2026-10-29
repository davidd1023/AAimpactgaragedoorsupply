{
    'name': "Work Order Sheet",
    # THE VERSION HAS TO CLEAR BOTH SIDES, NOT JUST THE BASE, and this file
    # has now watched that happen twice.
    #
    # On the 17th both branches reached 1.35.0 with different code - Prod's W/O
    # number and this branch's cancel-and-refund - and git merged the identical
    # line without a word, leaving a number a database already held and so
    # upgrading nothing at all. Hence 1.36.0.
    #
    # Then both reached 1.36.0 with different code again: Prod's Dispatched
    # button and this branch's merge. 1.37.0 clears both, so a database holding
    # either 1.36.0 still upgrades. Prod's 1.35.0 migration scripts continue to
    # run for anything below them.
    'version': '19.0.1.43.0',
    'summary': "Print a work order, and sort its work onto the benches",
    'description': """
Adds a printable sheet to a work order - the transfer the shop sees under
Operations > Work Orders (Pedidos) - listing every product on it, with the
length read out of the name for the ones that have one.

WORK STATIONS - PUT AWAY FOR NOW. Four bench kiosks sorted the work by the
same rule that splits the sheet into pages, and the owner has replaced them
with the shop floor module. Nothing is deleted: the files are no longer listed
in this manifest, a migration archived what an installed database already had,
and putting them back is four lines here and those records unarchived. See
views/work_station_picking_views.xml.

DELIVERY CONFIRMATION. Every delivery carries a link of its own: the customer
opens it on their phone, ticks what they were handed, types their name and
signs at the bottom. The form says when it was made and when it was signed,
both on the shop's clock, and what the customer did NOT tick goes into the
order's log for somebody to deal with.

The printed sheet stays on the transfer, which is the record it describes, and
the delivery confirmation never had anything to do with the benches - it hangs
off the outgoing transfer and the customer's own link.

CANCELLING A PAID ORDER. "Right now there is no defined process for this"
(owner, 2026-10-19), so there is one, on the order itself: Cancel & Refund.
The dialog states the procedure before it runs it, and then runs it in that
order:

  1. every unfinished job of the order comes off the Shop Floor;
  2. transfers that have not happened are cancelled, and transfers that have
     get a return raised against them for somebody to validate when the goods
     are physically back;
  3. the money goes back through whichever provider took it - Stripe can, a
     dealer account cannot and it says so rather than pretending;
  4. the order itself is cancelled, last, because the steps above need it.

It does NOT touch the ledger: a posted invoice stays posted, is named in the
order's log and needs a credit note from an accountant. The refund amount comes
in filled with what was taken and may be reduced for a restocking fee. Only a
Sales manager may do any of it, and the whole procedure - with who and why - is
written on the order.

SEPARATE FROM door_work_order ON PURPOSE. That module exists to receive a door
from the external calculator and raise a manufacturing order; this one prints
what a customer ordered on the website. They share a look and nothing else, and
this one depends on stock rather than mrp so it carries no manufacturing
machinery it does not use.
""",
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'author': 'AA Impact Garage Door Supply',
    'depends': ['stock', 'sale_stock', 'mrp', 'payment', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template_order_ready.xml',
        'data/cron_order_ready.xml',
        'data/customer_emails.xml',
        'data/wo_number_sequence.xml',
        'report/work_order_sheet_reports.xml',
        'views/delivery_templates.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'wizard/order_cancel_views.xml',
        'views/stock_picking_views.xml',
        'views/wo_number_views.xml',
        'views/dispatched_views.xml',
        'views/dispatch_scan_templates.xml',
        'report/dispatch_qr.xml',
        # THE WORK STATIONS, PUT AWAY FOR NOW - the owner's instruction,
        # 2026-10-14: the shop floor module does the same job. Nothing is
        # deleted; these three simply do not load, and a migration archives
        # what an installed database already has. Putting the benches back is
        # these three lines and unarchiving those records.
        #
        #   'views/station_templates.xml',
        #   'views/work_station_views.xml',
        #   'views/work_station_picking_views.xml',
        #   'data/work_station_data.xml',
    ],
    'installable': True,
    'application': False,
}
