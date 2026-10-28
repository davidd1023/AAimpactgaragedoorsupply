"""CANCELLING AN ORDER THAT HAS ALREADY BEEN PAID.

The owner, 2026-10-19: "Right now there is no defined process for this." So
this is the process, and the dialog IS the procedure - it says what the press
will do before anybody presses it, in the order it will do it:

  1. TAKE IT OFF THE SHOP FLOOR. Every job of the order that is not finished is
     cancelled, so nobody winds a spring for an order that no longer exists.
     Jobs already finished are left alone: they made something, and what
     happens to that is step 2.
  2. PUT THE GOODS BACK. Transfers that have not happened are cancelled.
     Transfers that HAVE happened get a return raised against them - goods
     already handed over or already moved to Output come back the way they
     went, which is a physical event somebody validates (owner's choice,
     2026-10-19).
  3. GIVE THE MONEY BACK, through whichever provider took it. Stripe supports
     refunds and Odoo routes it; a dealer account does not, and this says so
     plainly rather than pretending.
  4. CANCEL THE ORDER, last, because cancelling it first would cancel the
     transfers that step 2 still needs to return.

WHAT IT DOES NOT DO: touch the ledger. An invoice that has been posted stays
posted and the order's log says so, because a credit note is an accounting
entry and an accountant should decide to make it (owner's choice, 2026-10-19).

NOTHING IS ASSUMED ABOUT THE MONEY. The amount comes in filled with what was
actually taken and can be changed - a restocking fee, a part cancellation - and
whatever is typed is what is sent.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# The order is cancelled whatever happens to the rest; these are the states
# where there is nothing left to cancel.
SETTLED = ("done", "cancel")


class OrderCancel(models.TransientModel):
    _name = "aa.order.cancel"
    _description = "Cancel a paid order and refund it"

    order_id = fields.Many2one(
        "sale.order", string="Order", required=True, readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id")
    amount_total = fields.Monetary(
        related="order_id.amount_total", string="Order total")
    amount_paid = fields.Monetary(
        string="Taken", compute="_compute_amount_paid",
        help="What was actually taken through a payment provider that can "
             "give it back.")
    # ITS OWN COMPUTE, which matters more than it looks. Both figures were
    # worked out by one method to begin with, and because `amount_paid` is not
    # stored, every READ of it ran that method again and put the typed refund
    # back to the full amount: a 75 typed over a 100 was quietly refunded as
    # 100, by the guard that checks the typed figure against what was paid. A
    # test caught it. This one depends on the order alone, so it fills the box
    # once and never touches it again.
    amount_refund = fields.Monetary(
        string="Refund", compute="_compute_amount_refund", store=True,
        readonly=False,
        help="Filled in with what was taken. Change it for a part refund or a "
             "restocking fee; whatever is here is what is sent.")
    reason = fields.Char(
        string="Reason",
        help="Kept on the order's log, so the next person to look knows why.")
    plan = fields.Text(string="What this will do", compute="_compute_plan")
    can_refund = fields.Boolean(compute="_compute_amount_paid")

    # --- what is there to undo ------------------------------------------------

    def _refundable_transactions(self):
        """The order's payments that a provider can actually give back.

        A DEALER ACCOUNT CANNOT BE REFUNDED and neither can a wire transfer:
        there is no provider holding the money. Those are left for somebody to
        pay back by hand, and the dialog says so.
        """
        self.ensure_one()

        # READ WITH RAISED RIGHTS. transaction_ids is a restricted field on
        # the order - a salesperson cannot read it - and the owner asked for
        # anybody here to be able to cancel and refund. The gate in
        # action_cancel_and_refund is what authorises this; without the sudo
        # the dialog cannot even work out what was paid.
        return self.order_id.sudo().transaction_ids.filtered(
            lambda tx: tx.state == "done"
            and tx.operation != "refund"
            and tx.sudo().provider_id.support_refund)

    @api.depends("order_id")
    def _compute_amount_paid(self):
        for wizard in self:
            transactions = wizard._refundable_transactions()
            wizard.amount_paid = sum(transactions.mapped("amount"))
            wizard.can_refund = bool(transactions)

    @api.depends("order_id")
    def _compute_amount_refund(self):
        for wizard in self:
            wizard.amount_refund = wizard.amount_paid

    def _shop_floor_jobs(self):
        """The order's unfinished manufacturing orders, at any station.

        FOUND BY THE ORDER'S NAME, which is how every other part of this shop
        finds them: the station jobs carry it as their origin, and so do the
        prepared tracks Odoo's own route raises.
        """
        self.ensure_one()

        if not self.order_id.name:
            return self.env["mrp.production"]

        return self.env["mrp.production"].sudo().search([
            ("origin", "=", self.order_id.name),
            ("state", "not in", SETTLED),
        ])

    def _transfers(self):
        """(to cancel, to return) - the order's transfers, split by what has
        actually happened to them."""
        self.ensure_one()
        pickings = self.order_id.picking_ids

        return (pickings.filtered(lambda p: p.state not in SETTLED),
                pickings.filtered(lambda p: p.state == "done"))

    def _standing_invoices(self):
        """Posted invoices that will still be standing afterwards."""
        self.ensure_one()

        return self.order_id.invoice_ids.filtered(
            lambda move: move.state == "posted" and move.move_type == "out_invoice")

    @api.depends("order_id", "amount_refund")
    def _compute_plan(self):
        """THE PROCEDURE, IN WORDS, before anybody presses anything."""
        for wizard in self:
            order = wizard.order_id
            jobs = wizard._shop_floor_jobs()
            to_cancel, to_return = wizard._transfers()
            invoices = wizard._standing_invoices()
            lines = []

            if jobs:
                lines.append(_(
                    "Take %(count)s unfinished job(s) off the Shop Floor: %(names)s.",
                    count=len(jobs), names=", ".join(jobs.mapped("name"))))
            else:
                lines.append(_("Nothing to take off the Shop Floor."))

            if to_cancel:
                lines.append(_(
                    "Cancel %(count)s transfer(s) that have not happened: %(names)s.",
                    count=len(to_cancel), names=", ".join(to_cancel.mapped("name"))))

            if to_return:
                lines.append(_(
                    "Raise a return for %(count)s transfer(s) already done: "
                    "%(names)s. Somebody has to validate the return when the "
                    "goods are actually back.",
                    count=len(to_return), names=", ".join(to_return.mapped("name"))))

            if not to_cancel and not to_return:
                lines.append(_("No transfers to undo."))

            if wizard.can_refund:
                lines.append(_(
                    "Refund %(amount)s through %(provider)s.",
                    amount=wizard._money(wizard.amount_refund),
                    provider=", ".join(
                        wizard._refundable_transactions().sudo()
                        .mapped("provider_id.name"))))
            elif order.sudo().transaction_ids.filtered(lambda tx: tx.state == "done"):
                lines.append(_(
                    "No refund can be sent: this order was taken by a method "
                    "that cannot give money back (a dealer account or a "
                    "transfer). Pay it back by hand."))
            else:
                lines.append(_("Nothing was taken through a payment provider, "
                               "so there is nothing to refund."))

            if invoices:
                lines.append(_(
                    "Invoice %(names)s will still be standing. Issue a credit "
                    "note for it in Accounting - this does not touch the "
                    "ledger.",
                    names=", ".join(invoices.mapped("name"))))

            lines.append(_("Cancel the order itself."))
            wizard.plan = "\n".join("%d. %s" % (number, line)
                                    for number, line in enumerate(lines, 1))

    def _money(self, amount):
        self.ensure_one()

        return "%s %.2f" % (self.currency_id.symbol or "", amount or 0.0)

    # --- doing it -------------------------------------------------------------

    def action_cancel_and_refund(self):
        """The procedure, in the order the dialog promised."""
        self.ensure_one()

        # ANY EMPLOYEE MAY DO THIS (owner, 2026-10-19: "everyone should be
        # able to use and see the cancel and refund"). It was Sales managers
        # only; the shop is small enough that whoever picks up the phone when
        # a customer cancels is the person who should be able to act on it.
        #
        # INTERNAL USERS ONLY, THOUGH, and that is the line that matters: a
        # portal user must never be able to cancel and refund an order, their
        # own included.
        if not self.env.user.has_group("base.group_user"):
            raise AccessError(_(
                "Only somebody who works here can cancel a paid order and "
                "refund it."))

        order = self.order_id

        if order.state == "cancel":
            raise UserError(_("%s is already cancelled.", order.display_name))

        if self.amount_refund < 0:
            raise UserError(_("A refund cannot be less than nothing."))

        if self.amount_refund > self.amount_paid:
            raise UserError(_(
                "Only %(paid)s was taken, so %(asked)s cannot be given back.",
                paid=self._money(self.amount_paid),
                asked=self._money(self.amount_refund)))

        # THE CUSTOMER IS TOLD LAST, not when the first job comes off the
        # floor. Cancelling the shop floor jobs is now itself a reason to
        # send the cancellation email, and the three steps below it can still
        # fail - so an email sent at step 1 could promise a refund that never
        # happened. Held until _cancel_order, which knows what was given back.
        refunded = self._money(self.amount_refund) \
            if self.amount_refund and self.can_refund else ""
        held = self.with_context(aa_hold_cancel_email=True)

        done = []
        done += held._cancel_shop_floor()
        done += held._undo_transfers()
        done += held._refund()
        done += self.with_context(aa_refunded=refunded)._cancel_order()
        self._log(done)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("%s cancelled", order.name),
                "message": "\n".join(done),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _cancel_shop_floor(self):
        """Step 1: nobody makes anything for an order that is gone."""
        jobs = self._shop_floor_jobs()

        if not jobs:
            return [_("Nothing was on the Shop Floor.")]

        names = ", ".join(jobs.mapped("name"))
        stuck = []

        for job in jobs:
            # ONE JOB THAT WILL NOT CANCEL MUST NOT STOP THE REFUND. A
            # manufacturing order that has already consumed its components can
            # refuse, and the customer's money matters more than the tidiness
            # of the floor - the name is reported instead.
            try:
                with self.env.cr.savepoint():
                    job.sudo().action_cancel()
            except Exception:
                _logger.exception("work_order_sheet: cancelling %s failed", job.name)
                stuck.append(job.name)

        if stuck:
            return [_("Took the Shop Floor jobs off (%(names)s), except "
                      "%(stuck)s, which would not cancel - close those by hand.",
                      names=names, stuck=", ".join(stuck))]

        return [_("Took %(count)s job(s) off the Shop Floor: %(names)s.",
                  count=len(jobs), names=names)]

    def _undo_transfers(self):
        """Step 2: the goods go back where they came from."""
        to_cancel, to_return = self._transfers()
        said = []

        if to_cancel:
            to_cancel.sudo().action_cancel()
            said.append(_("Cancelled %(count)s transfer(s): %(names)s.",
                          count=len(to_cancel),
                          names=", ".join(to_cancel.mapped("name"))))

        returns = self.env["stock.picking"]

        for picking in to_return:
            returns |= self._return_picking(picking)

        if returns:
            said.append(_(
                "Raised %(count)s return(s): %(names)s. Validate them when the "
                "goods are actually back.",
                count=len(returns), names=", ".join(returns.mapped("name"))))

        return said or [_("There were no transfers to undo.")]

    def _return_picking(self, picking):
        """A return transfer for goods that have already moved, left in draft.

        NOT VALIDATED. Stock that is said to be back before anybody has
        actually put it back is a figure that lies, and the owner asked for
        the return to be raised rather than done.
        """
        # The picking is given rather than left to the context: the wizard
        # fills its lines from picking_id, and a wizard created without one
        # has nothing to return and says "specify at least one non-zero
        # quantity".
        wizard = self.env["stock.return.picking"].sudo().with_context(
            active_id=picking.id, active_model="stock.picking").create({
                "picking_id": picking.id})

        # THE QUANTITIES HAVE TO BE FILLED IN. Odoo's return wizard builds its
        # lines with quantity ZERO on purpose - the dialog exists for a person
        # to type how many are coming back - so asking it to create a return
        # straight away answers "specify at least one non-zero quantity". All
        # of it is coming back here, which is what a cancelled order means.
        for line in wizard.product_return_moves:
            line.quantity = line.move_id.quantity or line.move_id.product_uom_qty

        action = wizard.action_create_returns()
        created = action.get("res_id") if isinstance(action, dict) else False

        return self.env["stock.picking"].browse(created) if created \
            else self.env["stock.picking"]

    def _refund(self):
        """Step 3: the money, through whoever took it.

        WHY THERE IS NO REFUND COMES BEFORE WHETHER THERE IS ONE. My first
        draft checked the amount first, so a dealer-account order - which has
        nothing refundable and therefore an amount of zero - was logged as "no
        money was sent back", which reads like a decision rather than the fact
        that nobody can send it. A test caught it against what the dialog had
        already promised.
        """
        transactions = self._refundable_transactions()

        if not transactions:
            taken = self.order_id.sudo().transaction_ids.filtered(
                lambda tx: tx.state == "done" and tx.operation != "refund")

            if taken:
                return [_("There is no payment here that can be refunded - the "
                          "money was taken by a method that cannot give it "
                          "back, so pay it back by hand.")]

            return [_("Nothing was taken through a payment provider, so there "
                      "was nothing to refund.")]

        if not self.amount_refund:
            return [_("No money was sent back.")]

        left = self.amount_refund
        sent = []

        # SPREAD OVER THE PAYMENTS THAT WERE TAKEN, oldest first, because an
        # order can have been paid in more than one go and no single provider
        # can give back more than it took.
        for transaction in transactions.sorted("id"):
            if left <= 0:
                break

            share = min(left, transaction.amount)
            # RAISED RIGHTS, AUTHORISED ABOVE. Odoo checks write access on the
            # transaction before refunding, which a plain employee does not
            # have; the permission question is answered once, by the check at
            # the top, and the log below records who actually pressed it.
            transaction.sudo().action_refund(amount_to_refund=share)
            left -= share
            sent.append(transaction.reference)

        return [_("Sent %(amount)s back through %(references)s.",
                  amount=self._money(self.amount_refund - max(left, 0)),
                  references=", ".join(sent))]

    def _cancel_order(self):
        """Step 4: last, because the steps above needed it alive.

        AND THE CUSTOMER IS TOLD. There was no cancellation email anywhere -
        Odoo does not send one and this procedure did not either - so somebody
        whose paid order was cancelled heard nothing at all until they rang up
        (owner, 2026-10-19: it is one of the four emails a customer gets).
        """
        order = self.order_id

        # SENT BY _action_cancel NOW, not here, because this is no longer the
        # only way an order gets cancelled (models/order_cancelled_email.py).
        # One sender, one stamp on the order, so cancelling again in Sales or
        # in Manufacturing cannot send the same news twice.
        order.sudo()._action_cancel()

        if order.aa_cancel_email_sent:
            return [_("Cancelled %s, and told the customer.", order.name)]

        return [_("Cancelled %s. There is no email address on file, so "
                  "nobody was told.", order.name)]

    def _log(self, done):
        """The whole procedure, written on the order, with who and why."""
        invoices = self._standing_invoices()
        body = [_("<b>Cancelled and refunded</b> by %s.",
                  self.env.user.display_name)]

        if self.reason:
            body.append(_("Reason: %s", self.reason))

        body += done

        if invoices:
            body.append(_(
                "<b>Invoice %s is still standing</b> and needs a credit note.",
                ", ".join(invoices.mapped("name"))))

        self.order_id.sudo().message_post(body="<br/>".join(body))
