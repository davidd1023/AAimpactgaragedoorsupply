from odoo import SUPERUSER_ID, api

# THE TWO ORDERS ALREADY OPEN when the W/O number came in (owner, 2026-10-19):
# "por el 200, ponle a esas dos 200 y 201". New orders carry on from #202,
# which is where the sequence file starts.
EXISTING = (
    ("S00036", "W/O #200"),
    ("S00037", "W/O #201"),
)
FIRST_NEW = 202


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sale = env["sale.order"]

    for order_name, number in EXISTING:
        order = Sale.search([("name", "=", order_name)], limit=1)
        if not order or order.aa_wo_number:
            continue
        if Sale.search_count([("aa_wo_number", "=", number)]):
            continue
        order.aa_wo_number = number
        order._aa_name_work_order_transfer()

    # The sequence must never hand out a number already taken.
    sequence = env.ref("work_order_sheet.sequence_aa_work_order_number", raise_if_not_found=False)
    if sequence and sequence.number_next_actual < FIRST_NEW:
        sequence.number_next_actual = FIRST_NEW

    # ANY OTHER ORDER STILL OPEN - confirmed, not yet fully delivered - takes
    # the next number, oldest first, so nothing on the floor is left without
    # one (an order confirmed in production between the request and the
    # update, e.g. S00040).
    if sequence:
        still_open = Sale.search([
            ("state", "=", "sale"),
            ("aa_wo_number", "=", False),
            ("delivery_status", "!=", "full"),
        ], order="date_order, id")
        for order in still_open:
            order.aa_wo_number = sequence.next_by_id()
            order._aa_name_work_order_transfer()

    # The new stored columns were filled before the orders had a number.
    pickings = env["stock.picking"].search([("origin", "!=", False)])
    pickings._compute_aa_wo_number()
    productions = env["mrp.production"].search([("origin", "!=", False)])
    productions._compute_aa_wo_number()
    env.flush_all()
