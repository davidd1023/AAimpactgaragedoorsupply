"""TELLING THE CUSTOMER THEIR ORDER IS CANCELLED - ONCE, WHOEVER CANCELS IT.

Owner, 2026-10-27: *"i need you to make it so the user gets an email when
their order is cancelled, specifically when it gets cancelled on
manufacturing, i dont want to send multiple emails if i also have to cancel it
again in the sales module or some other module that isn't manufacturing."*

Two requirements in one sentence, and the second is the harder one. An order
is cancelled in several places - the cancel-and-refund wizard, Odoo's own
Cancel in Sales, and now Manufacturing - and he cancels in more than one of
them for the same order. So the rule is not "send from manufacturing" but
**send once per order, from whichever place gets there first**.

That is what `aa_cancel_email_sent` is: a stamp on the order saying the
customer has been told, written the moment the mail goes. Every path asks the
same method, and the second and third paths find the stamp already there and
do nothing. A flag rather than searching the chatter for a previous email,
because a message that failed to send still leaves a message.

### WHEN MANUFACTURING COUNTS AS CANCELLING THE ORDER

An order is not one job. Confirming it raises a Springs job, a Pack hardware
kit job, a Cut lift cables job, and Odoo's own route may raise a prepared
track job on top - so cancelling ONE of them does not mean the order is
cancelled, it means one part of it changed. Asked which he wanted, the owner
chose the email to go **when nothing is left being made**: the last of that
order's jobs being cancelled, not the first.

Where some jobs were already finished and the rest are cancelled, no email
goes from here - parts of that order were built, and cancelling it properly
is then a Sales job, which sends from the other path.

### THE WIZARD HOLDS IT BACK UNTIL THE MONEY IS SETTLED

The cancel-and-refund wizard cancels the shop floor jobs FIRST and refunds
afterwards, so without care the "your order is cancelled, $X refunded" email
would go out before the refund had been attempted - and be a promise if it
then failed. It runs its first three steps under `aa_hold_cancel_email` and
sends at the end, by which time it also knows what was actually given back.
"""

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    aa_cancel_email_sent = fields.Datetime(
        string="Cancellation Emailed", copy=False, readonly=True,
        help="When the customer was told this order was cancelled. Set once, "
             "by whichever place cancelled it first, so the same news is not "
             "sent twice.")

    # --- who is making what for this order ---------------------------------

    def _aa_manufacturing_orders(self):
        """Every job raised for this order, by either link there is.

        The station jobs carry `aa_sale_line_id`, which is exact. A prepared
        track job comes from Odoo's own route and carries no such field, only
        the order's name in `origin` - so both are asked, and the field is
        checked for because it belongs to aa_shop_floor and this module does
        not depend on it.
        """
        self.ensure_one()
        productions = self.env["mrp.production"].sudo()
        found = productions.browse()

        if "aa_sale_line_id" in productions._fields:
            found |= productions.search(
                [("aa_sale_line_id.order_id", "=", self.id)])

        if self.name:
            found |= productions.search([("origin", "=", self.name)])

        return found

    def _aa_nothing_left_being_made(self):
        """True when every job for this order has been cancelled.

        A job that is DONE is deliberately not counted as nothing: something
        was built, and "your order is cancelled" is the wrong thing to say
        about an order that was half made. That case is a Sales cancellation,
        which has its own path to this email.
        """
        self.ensure_one()
        jobs = self._aa_manufacturing_orders()

        return bool(jobs) and all(job.state == "cancel" for job in jobs)

    # --- the one sender ----------------------------------------------------

    def _aa_send_cancellation_email(self):
        """Tell the customer, unless they have already been told.

        :return: the orders an email actually went out for.
        """
        if self.env.context.get("aa_hold_cancel_email"):
            return self.browse()

        template = self.env.ref(
            "work_order_sheet.mail_template_order_cancelled",
            raise_if_not_found=False)

        if not template:
            return self.browse()

        told = self.browse()

        for order in self:
            if order.aa_cancel_email_sent or not order.partner_id.email:
                continue

            # STAMPED BEFORE SENDING, not after. send_mail with force_send
            # can re-enter - the mail layout renders the order, and anything
            # that touches it again would find no stamp and send a second.
            order.sudo().aa_cancel_email_sent = fields.Datetime.now()
            template.sudo().send_mail(order.id, force_send=True)
            told |= order

        return told

    # --- cancelled from Sales, or from anywhere else -----------------------

    def _action_cancel(self):
        """Odoo's own path, which is every cancellation that is not a job.

        Only for an order the customer actually placed: a quotation that was
        never confirmed has nothing to cancel as far as they are concerned,
        and telling somebody their order is off when they never had one is
        worse than silence.
        """
        placed = self.filtered(lambda order: order.state in ("sale", "done"))
        result = super()._action_cancel()
        placed._aa_send_cancellation_email()

        return result


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _aa_customer_order(self):
        """The order this job was raised for, or an empty recordset."""
        self.ensure_one()

        if "aa_sale_line_id" in self._fields:
            line = self.aa_sale_line_id

            if line and line.exists() and line.order_id:
                return line.order_id

        if self.origin:
            return self.env["sale.order"].sudo().search(
                [("name", "=", self.origin)], limit=1)

        return self.env["sale.order"].browse()

    def action_cancel(self):
        """Cancelling the last job for an order cancels it, as far as the
        customer is concerned.

        The orders are collected BEFORE the cancellation, because that is when
        the links are certain to still be readable, and asked afterwards -
        when the states have moved - whether anything is left being made.
        """
        orders = self.env["sale.order"].browse()

        for production in self:
            orders |= production._aa_customer_order()

        result = super().action_cancel()

        for order in orders:
            if order.exists() and order._aa_nothing_left_being_made():
                order._aa_send_cancellation_email()

        return result
