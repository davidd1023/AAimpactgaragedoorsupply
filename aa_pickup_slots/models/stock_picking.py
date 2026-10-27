"""THE SLOT, ON THE PAPERWORK THE SHOP ACTUALLY LOOKS AT.

Owner, 2026-10-27: *"it shows on the Work Order and in Dispatch. Done when:
the chosen slot appears on the order and the Dispatch list."*

STORED ON THE TRANSFER, not read through the sale order. The Dispatch list is
a list of transfers and the first thing anybody wants to do with a pickup time
is SORT BY IT - who is coming this morning - and a related field through
`sale_id` cannot be ordered on in the database. It is written at confirmation
and left alone after, so a slot changed later needs writing again; that is the
trade for a column that sorts.
"""

from odoo import api, fields, models

from .pickup_time import time_label


class StockPicking(models.Model):
    _inherit = "stock.picking"

    aa_pickup_date = fields.Date(
        string="Pickup Day", copy=False, index=True)
    aa_pickup_time = fields.Float(
        string="Pickup Time", copy=False, digits=(4, 2))
    aa_pickup_label = fields.Char(
        string="Pickup", compute="_compute_aa_pickup_label", store=True)

    @api.depends("aa_pickup_date", "aa_pickup_time")
    def _compute_aa_pickup_label(self):
        for picking in self:
            if not picking.aa_pickup_date:
                picking.aa_pickup_label = False
                continue

            day = picking.aa_pickup_date.strftime("%a %-d %b")
            at = (time_label(picking.aa_pickup_time)
                  if picking.aa_pickup_time else "")
            picking.aa_pickup_label = "%s, %s" % (day, at) if at else day
