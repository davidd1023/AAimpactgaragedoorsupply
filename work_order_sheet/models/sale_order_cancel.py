"""The button on the order that opens the cancel-and-refund procedure."""

from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_aa_cancel_and_refund(self):
        """Open the procedure for this order.

        A WIZARD RATHER THAN A BUTTON THAT ACTS. What this does cannot be
        undone - money leaves, jobs stop, transfers unwind - so it says what it
        is about to do and waits to be told to go ahead.
        """
        self.ensure_one()

        if self.state == "cancel":
            raise UserError(_("%s is already cancelled.", self.display_name))

        return {
            "type": "ir.actions.act_window",
            "name": _("Cancel and refund %s", self.name),
            "res_model": "aa.order.cancel",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }
