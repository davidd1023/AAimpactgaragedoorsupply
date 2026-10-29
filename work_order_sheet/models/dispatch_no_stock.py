"""DISPATCHED FOR THE RECORD, WITHOUT USING ANY STOCK.

Owner, 2026-10-29: *"can you do the dispatch with no inventory adjustment and
put it in the actions menu ... when clicking it make a warning that says
something like 'Warning: this is only for orders that used no actual inventory
and is only to be used for records or testing, not for real orders'."*

**ODOO WILL NOT LET A TRANSFER BE DONE WHILE MOVING NOTHING** - its own sanity
check says so in as many words, and the two obvious ways round it were tried
and measured before this was written:

  * all quantities at NOUGHT, with `skip_sanity_check`: `_action_done`
    CANCELS a zero-quantity move, so the transfer ends up **Cancelled**, not
    dispatched. Stock untouched, but it is not "sent".
  * dispatching with an empty rack: Odoo does not block at all, it simply
    takes the quant **negative**. That is the opposite of what he asked for.

**SO EVERY LINE IS DELIVERED TO WHERE IT CAME FROM.** The move is done at its
full quantity through Odoo's own machinery - so the transfer is genuinely
Done and the sale order genuinely reads as delivered - and because the source
and the destination are the same quant, the decrement and the increment are
the same number and cancel exactly. Measured: 45 on hand before, 45 after, 50
in the building either way.

**THE CHATTER SAYS WHAT HAPPENED**, in plain words, because a transfer that
reads Done while the shelf never moved is a lie unless somebody wrote it
down. Anyone looking at this order in six months needs to know why its stock
never went anywhere.

**STOCK MANAGERS ONLY.** This is a tool for straightening records, and in the
wrong hands on a real order it silently breaks the count of whatever was on
it. His own warning says as much; the group makes it true.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: His words, near enough verbatim (2026-10-29).
WARNING = _(
    "Warning: this is only for orders that used no actual inventory and is "
    "only to be used for records or testing, not for real orders."
)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_aa_dispatch_no_stock_wizard(self):
        """Open the warning. The Actions menu entry calls this."""
        return {
            "type": "ir.actions.act_window",
            "res_model": "aa.dispatch.no.stock",
            "view_mode": "form",
            "target": "new",
            "name": _("Dispatch Without Using Inventory"),
            "context": dict(self.env.context, active_ids=self.ids),
        }

    def _aa_dispatch_without_stock(self):
        """Mark this transfer sent, moving nothing. Returns True if it did.

        Raises nothing for a transfer that was already settled: the caller is
        working on a selection of thirty and one of them being done already is
        not a reason to abandon the other twenty-nine.
        """
        self.ensure_one()

        if self.state in ("done", "cancel"):
            return False

        for move in self.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")):
            # Full quantity, so the move is real enough for Odoo to finish it
            # rather than cancelling it as empty.
            move.quantity = move.product_uom_qty
            move.picked = True

            if not move.move_line_ids:
                self.env["stock.move.line"].create({
                    "move_id": move.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_id.id,
                    "quantity": move.product_uom_qty,
                    "picking_id": self.id,
                })

            # WHERE IT CAME FROM IS WHERE IT GOES. Same quant in and out, so
            # the two cancel and nothing on any shelf changes.
            for line in move.move_line_ids:
                line.location_dest_id = line.location_id

        self.with_context(
            skip_backorder=True,
            picking_ids_not_to_backorder=self.ids,
        ).button_validate()

        if self.state != "done":
            return False

        self.write({"aa_dispatched_by": self.env.uid,
                    "aa_dispatched_on": fields.Datetime.now()})
        self.message_post(body=_(
            "Marked dispatched WITHOUT USING INVENTORY by %(user)s. Every "
            "line was delivered to the location it came from, so no stock "
            "moved. For records or testing only.",
            user=self.env.user.name), subtype_xmlid="mail.mt_note")

        return True


class AaDispatchNoStock(models.TransientModel):
    _name = "aa.dispatch.no.stock"
    _description = "Dispatch Without Using Inventory"

    picking_ids = fields.Many2many(
        "stock.picking", string="Transfers", required=True)
    warning = fields.Char(default=lambda self: WARNING, readonly=True)
    settled_count = fields.Integer(
        string="Already Settled", compute="_compute_counts")
    to_do_count = fields.Integer(string="To Dispatch", compute="_compute_counts")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        ids = self.env.context.get("active_ids") or []

        if not ids:
            raise UserError(_("Choose the transfers to dispatch first."))

        values["picking_ids"] = [(6, 0, ids)]

        return values

    @api.depends("picking_ids.state")
    def _compute_counts(self):
        for wizard in self:
            settled = wizard.picking_ids.filtered(
                lambda p: p.state in ("done", "cancel"))
            wizard.settled_count = len(settled)
            wizard.to_do_count = len(wizard.picking_ids) - len(settled)

    def action_confirm(self):
        """Do it, and say how many it did."""
        self.ensure_one()
        done, refused = 0, []

        for picking in self.picking_ids:
            try:
                if picking._aa_dispatch_without_stock():
                    done += 1
                else:
                    refused.append(picking.display_name)
            except UserError as error:
                # ONE AWKWARD TRANSFER DOES NOT ABANDON THE OTHER TWENTY-NINE.
                refused.append("%s (%s)" % (picking.display_name,
                                            error.args[0]))

        message = _("%s marked dispatched without using inventory.", done)

        if refused:
            message += _(" %(count)s left alone: %(detail)s",
                         count=len(refused), detail="; ".join(refused[:5]))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Dispatch Without Using Inventory"),
                       "message": message,
                       "type": "warning" if refused else "success",
                       "sticky": True,
                       "next": {"type": "ir.actions.act_window_close"}},
        }
