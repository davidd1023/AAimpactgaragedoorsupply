"""SCAN THE QR TO DISPATCH.

Owner, 2026-10-28: *"At pickup, the team scans the box sticker with a phone or
tablet. Odoo opens that order, checks every station is done and the invoice is
paid, and marks it Dispatched in one tap. the qr should be on one of the form
that is printed out at dispatch."*

THE ACTION ALREADY EXISTED - `action_aa_dispatched` has been the one button
since 2026-10-19, and it validates the transfer, records who sent it out and
drops the order off the To Dispatch list. What is new is a way to reach it
with a phone, and two checks worth making while somebody is standing there
with the box.

**IT IS NOT A PUBLIC LINK, and that is the one way it differs from the box
sticker next door.** `/box/...` only tells you what is in a box; the worst a
leaked link can do is read out a door's figures, which is what the sticker
itself does. THIS ONE CHANGES THE BOOKS. A public link that marked an order
collected would let anybody who photographed a form empty the dispatch list.
So the page asks for a login and for `stock.group_stock_user`, which on a
tablet means signing in once. The token is still there, because a URL that is
only an id is a URL somebody edits.

THE TWO CHECKS, and what happens when they fail - both his call, asked
2026-10-28:

  * **UNPAID BLOCKS, with no way round it.** The button is dead and says why.
    Money is not a thing for a judgement call at the counter.
  * **AN UNFINISHED STATION WARNS.** It shows in red and the team can still
    dispatch with a second tap, because a foreman can see the box is packed
    and the system is sometimes behind the shop.

**THE CHECKS READ WITH SUDO; THE DISPATCH DOES NOT.** A dispatch clerk is in
`stock.group_stock_user` and that is all - they cannot read `account.move`,
and the first build answered 403 the moment the page asked whether an invoice
was paid. Being TOLD "paid" is not the same as being allowed to open the
ledger, so the two checks are read as superuser and the page is rendered from
sudo'd records. The DISPATCH itself is still done as the person standing
there, so Odoo's own rights apply to it and `aa_dispatched_by` is a name that
means something.

**A DEALER ON ACCOUNT PASSES THE PAYMENT CHECK.** A Quick Order charged to
account raises no invoice at the time (CLAUDE.md, 2026-10-27), so "no paid
invoice" would have blocked every dealer collection there is. The page says
ON ACCOUNT rather than UNPAID, which is the truth and reads differently to
whoever is holding the box.
"""

from urllib.parse import quote

from odoo import _, models
from odoo.tools import consteq
from odoo.tools.misc import hmac

#: An invoice in any of these is money we have.
SETTLED = ("paid", "in_payment", "reversed")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # --- the link the QR code holds ---------------------------------------

    def _aa_dispatch_token(self):
        """The secret half of this transfer's link.

        DERIVED, NOT STORED, the same way the box sticker's is: a form printed
        today still scans next week, there is no column to migrate or leak,
        and one transfer's token says nothing about another's.
        """
        self.ensure_one()

        return hmac(self.env(su=True), "work_order_sheet.dispatch",
                    (self.id,))[:24]

    def _aa_dispatch_url(self):
        """The whole link, for the QR code on the printed forms."""
        self.ensure_one()
        base = (self.get_base_url() or "").rstrip("/")

        return "%s/dispatch/%d/%s" % (base, self.id, self._aa_dispatch_token())

    def _aa_dispatch_qr_src(self, size=220):
        """Odoo's own barcode image route, built HERE rather than in QWeb.

        The sticker next door does the same: a template has no business
        quoting a URL, and `quote(..., safe="")` is the whole reason the link
        survives being a query parameter.
        """
        self.ensure_one()

        return "/report/barcode/?barcode_type=QR&value=%s&width=%d&height=%d" % (
            quote(self._aa_dispatch_url(), safe=""), size, size)

    def _aa_dispatch_scan_ok(self, token):
        """Does this token open this transfer? Constant time, so the route
        cannot be turned into a way of measuring how close a guess was."""
        self.ensure_one()

        return consteq(token or "", self._aa_dispatch_token())

    # --- what the scan has to check ---------------------------------------

    def _aa_dispatch_sale_order(self):
        """The order behind this transfer, by either route.

        SUDO, because a dispatch clerk has stock rights and nothing else.
        """
        self.ensure_one()
        picking = self.sudo()

        if picking.sale_id:
            return picking.sale_id

        if hasattr(picking, "_work_order_sale_order"):
            return picking._work_order_sale_order()

        return self.env["sale.order"].sudo().browse()

    def _aa_on_account(self, order):
        """Is this order charged to a dealer's account?

        Asked through `_fields` because `aa_order_on_account` belongs to
        `aa_dealer_orders` and this module does not depend on it - the same
        arrangement the cancellation email uses for `aa_sale_line_id`.
        """
        if not order or "aa_order_on_account" not in self.env["res.partner"]._fields:
            return False

        partner = order.partner_id

        return bool(partner.aa_order_on_account
                    or partner.commercial_partner_id.aa_order_on_account)

    def _aa_dispatch_payment(self):
        """(settled, wording) - whether the money is in, and what to say."""
        self.ensure_one()
        order = self._aa_dispatch_sale_order()

        if not order:
            # Nothing to check against. A transfer with no sale order behind
            # it was made in the back office by somebody who knows what it is
            # for, and inventing a debt for it would be a lie.
            return True, _("No sale order - nothing to collect")

        invoices = order.sudo().invoice_ids.filtered(
            lambda move: move.state != "cancel")

        if invoices:
            if all(move.payment_state in SETTLED for move in invoices):
                return True, _("Paid")

            return False, _("NOT PAID - %s") % ", ".join(
                sorted({move.payment_state or "draft" for move in invoices}))

        if self._aa_on_account(order):
            # HIS DECISION, 2026-10-28. No invoice because it is charged to
            # account is not the same as no invoice because nobody has paid.
            return True, _("On account - invoiced later")

        return False, _("NOT PAID - no invoice has been raised")

    def _aa_dispatch_stations(self):
        """(finished, [what is still open]) across this order's jobs."""
        self.ensure_one()
        order = self._aa_dispatch_sale_order()

        if not order or not hasattr(order, "_aa_manufacturing_orders"):
            return True, []

        jobs = order.sudo()._aa_manufacturing_orders()
        open_jobs = jobs.filtered(lambda job: job.state not in ("done", "cancel"))

        return not open_jobs, [
            "%s (%s)" % (job.display_name, job.state) for job in open_jobs]

    def _aa_dispatch_scan_state(self):
        """Everything the scan page and its button need, worked out once."""
        self.ensure_one()
        paid, payment = self._aa_dispatch_payment()
        finished, open_jobs = self._aa_dispatch_stations()
        order = self._aa_dispatch_sale_order()

        return {
            # SUDO'D FOR THE PAGE. Everything below is read-only and the
            # person is already known to be on the dispatch desk; what they
            # must not need is the right to open an invoice.
            "picking": self.sudo(),
            "order": order.sudo() if order else order,
            "paid": paid,
            "payment": payment,
            "finished": finished,
            "open_jobs": open_jobs,
            # ALREADY GONE is not a failure, it is an answer: somebody scans
            # the same form twice and should be told so rather than shown a
            # button that will raise.
            "already": bool(self.aa_dispatched_on),
            "ready": self.state == "assigned",
            # UNPAID IS THE ONLY BAR. An open station is a warning the team
            # can go past with a second tap (his call, 2026-10-28).
            "can_dispatch": (paid and self.state == "assigned"
                             and not self.aa_dispatched_on),
            "needs_confirm": not finished,
        }
