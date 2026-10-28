"""THE SLOT, ON THE PAPERWORK THE SHOP ACTUALLY LOOKS AT.

Owner, 2026-10-27: *"it shows on the Work Order and in Dispatch. Done when:
the chosen slot appears on the order and the Dispatch list."*

STORED ON THE TRANSFER, not read through the sale order. The Dispatch list is
a list of transfers and the first thing anybody wants to do with a pickup time
is SORT BY IT - who is coming this morning - and a related field through
`sale_id` cannot be ordered on in the database.

A STORED COPY HAS TO BE KEPT IN STEP, and the first cut was not. It was
written once, at confirmation, which left two holes the owner would have found
at the counter:

  * A BACKORDER CARRIES NOTHING. Odoo makes one by copying the transfer, and
    these fields are `copy=False` - deliberately, so duplicating an order does
    not inherit somebody else's collection day. So the half of the order the
    customer actually comes back for showed a blank Pickup column. `create`
    now fills it from the sale order whenever it is not given.
  * A SLOT MOVED AFTER CONFIRMATION STAYED ON THE OLD DAY. `sale.order.write`
    now pushes the change down to the transfers still to go out.

Transfers already DONE or CANCELLED are left alone: what happened, happened.
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

    # --- a transfer born after the order was confirmed --------------------

    @api.model_create_multi
    def create(self, vals_list):
        """A backorder inherits the slot its order was given.

        `copy=False` keeps the day off a DUPLICATED order, which is right -
        but a backorder is the same order's remaining half, and the customer
        is coming for it on the day they said.
        """
        pickings = super().create(vals_list)

        for picking, vals in zip(pickings, vals_list):
            if "aa_pickup_date" in vals or not picking.sale_id:
                continue

            order = picking.sale_id

            if order.aa_pickup_date:
                picking.write({
                    "aa_pickup_date": order.aa_pickup_date,
                    "aa_pickup_time": order.aa_pickup_time,
                })

        return pickings

    def _aa_open_for_pickup(self):
        """The transfers a changed slot still means something to."""
        return self.filtered(lambda p: p.state not in ("done", "cancel"))
