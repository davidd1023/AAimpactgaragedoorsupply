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

from .pickup_time import slot_in_utc, time_label


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

    # --- the slot IS the scheduled date -----------------------------------

    def _aa_pickup_datetime(self):
        """When this transfer is due, from the slot the customer chose."""
        self.ensure_one()

        return slot_in_utc(self.env, self.aa_pickup_date, self.aa_pickup_time)

    def _aa_sync_pickup_schedule(self):
        """Put the chosen slot on Odoo's own Scheduled Date.

        Owner, 2026-10-29, with a screenshot of W/O #268: *"when the customer
        selects their order date it should be the scheduled date in the work
        order, but currently the schedule date is the same as the time it was
        ordered and the actual scheduled date is next to it."*

        He is right that they were two things side by side. Odoo set
        `scheduled_date` the moment the order was confirmed - which is when it
        was ORDERED, not when anybody wants it - and this module printed the
        real answer in the field beside it. The shop had to read the second
        one and ignore the first.

        **ONE PLACE, ON `write`.** The slot reaches a transfer by three
        different roads - confirmation, a slot moved afterwards, and a
        backorder copying its order - and keeping a stored copy in step
        across three of them is exactly what went wrong with the Pickup
        column itself. Every one of them ends in a `write` of these two
        fields, so the rule lives there and cannot be forgotten by a fourth.

        **DONE AND CANCELLED ARE LEFT ALONE**, as everywhere else here: what
        was on the paperwork is a record.

        **AND IT ONLY MOVES WHEN THE SLOT DOES.** Somebody who sets a
        scheduled date by hand for a reason of their own keeps it; this is
        not a rule that reaches in and overwrites planning every time the
        transfer is saved.
        """
        for picking in self:
            if picking.state in ("done", "cancel") or not picking.aa_pickup_date:
                continue

            due = picking._aa_pickup_datetime()

            if due and picking.scheduled_date != due:
                super(StockPicking, picking).write({"scheduled_date": due})

    def write(self, vals):
        result = super().write(vals)

        if "aa_pickup_date" in vals or "aa_pickup_time" in vals:
            self._aa_sync_pickup_schedule()

        return result

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

        # A transfer CREATED with the slot already in its values never passed
        # through the write above, so the rule is applied here as well.
        pickings.filtered("aa_pickup_date")._aa_sync_pickup_schedule()

        return pickings

    def _aa_open_for_pickup(self):
        """The transfers a changed slot still means something to."""
        return self.filtered(lambda p: p.state not in ("done", "cancel"))
