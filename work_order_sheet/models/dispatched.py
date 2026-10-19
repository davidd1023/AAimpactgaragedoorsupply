from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # DISPATCHED IS A PERSON SAYING SO (owner, 2026-10-19): the order is gone
    # when somebody at the door confirms it went, not when the customer signs.
    # One button on the dispatch does it: the transfer is validated, the
    # stock leaves, and the order drops off the To Dispatch list.
    aa_dispatched_by = fields.Many2one(
        "res.users", string="Dispatched by", copy=False, readonly=True)
    aa_dispatched_on = fields.Datetime(
        string="Dispatched on", copy=False, readonly=True)
    # Signed, and every item ticked. Anything less asks before dispatching.
    aa_dispatch_clean = fields.Boolean(
        string="Signed for in full", compute="_compute_aa_dispatch_clean")

    @api.depends("dispatch_signed_on", "move_ids.dispatch_received", "move_ids.state")
    def _compute_aa_dispatch_clean(self):
        for picking in self:
            lines = picking._dispatch_lines() if picking.id else picking.move_ids
            picking.aa_dispatch_clean = bool(
                picking.dispatch_signed_on and lines
                and all(move.dispatch_received for move in lines))

    def action_aa_dispatched(self):
        """The Dispatched button. Validates the delivery as it stands - every
        line at its full quantity, which is what Ready means - and records
        who sent it out and when, on the delivery and on the sale order."""
        self.ensure_one()
        if self.picking_type_code != "outgoing":
            raise UserError(_("Only a delivery can be dispatched."))
        if self.state != "assigned":
            raise UserError(_("%s is not ready to go out yet.", self.display_name))

        for move in self.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
            if move.product_uom.compare(move.quantity, move.product_uom_qty) < 0:
                move.quantity = move.product_uom_qty
            move.picked = True

        result = self.button_validate()
        if self.state != "done":
            # Odoo asked something first (a lot number, a backorder...): hand
            # its question to the user; nothing is recorded until it is done.
            return result

        self.write({"aa_dispatched_by": self.env.uid,
                    "aa_dispatched_on": fields.Datetime.now()})
        self._aa_log_dispatched()
        return result

    def _aa_log_dispatched(self):
        when = fields.Datetime.context_timestamp(self, self.aa_dispatched_on)
        text = _("Dispatched by %(user)s, %(when)s",
                 user=self.aa_dispatched_by.name,
                 when=when.strftime("%b %d, %I:%M %p"))
        if self.aa_wo_number:
            text += ", %s" % self.aa_wo_number
        if not self.dispatch_signed_on:
            text += Markup(" — <b>%s</b>") % _("the customer had not signed")
        elif not self.aa_dispatch_clean:
            text += Markup(" — <b>%s</b>") % _("the customer did not tick every item")
        body = Markup("<p>%s</p>") % text
        self.message_post(body=body, subtype_xmlid="mail.mt_note")
        order = self.sale_id or self._work_order_sale_order()
        if order:
            order.message_post(body=body, subtype_xmlid="mail.mt_note")
