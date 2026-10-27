"""THE TRANSFERS THAT WERE MADE BEFORE THE COPY WAS KEPT IN STEP.

Owner, 2026-10-27: *"i dont see the scheduled pickup date on the dispatch
screen, it showed up in manufacturing but not in dispatch."*

The slot was written onto the transfers once, at confirmation. A BACKORDER is
made afterwards, by copying - and these fields are `copy=False` - so the half
of the order the customer actually comes back for carried nothing. Any
transfer standing open against an order that has a slot is filled in here,
rather than waiting for somebody to touch the order again.

Transfers already DONE or CANCELLED are left as they are: what was on the
paperwork when it went out the door is a record, not a field to tidy.

Written through the ORM rather than in SQL, because the label beside the day
is a STORED COMPUTE: an UPDATE would set the two columns Dispatch sorts on and
leave the one it reads blank, which is the same bug in a new place.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    pickings = env["stock.picking"].search([
        ("state", "not in", ("done", "cancel")),
        ("aa_pickup_date", "=", False),
        ("sale_id.aa_pickup_date", "!=", False),
    ])

    for picking in pickings:
        picking.write({
            "aa_pickup_date": picking.sale_id.aa_pickup_date,
            "aa_pickup_time": picking.sale_id.aa_pickup_time,
        })

    if pickings:
        _logger.info(
            "aa_pickup_slots: %s transfers were missing their pickup slot",
            len(pickings))
