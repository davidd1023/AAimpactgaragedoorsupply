"""THE SLOT BECOMES THE SCHEDULED DATE ON ORDERS ALREADY TAKEN.

Owner, 2026-10-29, with a screenshot of W/O #268: *"when the customer selects
their order date it should be the scheduled date in the work order, but
currently the schedule date is the same as the time it was ordered and the
actual scheduled date is next to it."*

Every transfer confirmed before this still carries the moment it was ORDERED
as its Scheduled Date, with the real answer in the field beside it. W/O #268
is one of them, and the shop has a list of them.

OPEN TRANSFERS ONLY. A finished one is a record of what happened, and this
module has left those alone everywhere since the slot was first stored.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    pickings = env["stock.picking"].search([
        ("aa_pickup_date", "!=", False),
        ("state", "not in", ("done", "cancel")),
    ])

    pickings._aa_sync_pickup_schedule()

    _logger.info("aa_pickup_slots: %s transfers scheduled for the slot the "
                 "customer chose", len(pickings))
