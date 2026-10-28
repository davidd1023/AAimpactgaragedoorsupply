"""SCAN THE QR TO DISPATCH.

Owner, 2026-10-28: *"At pickup, the team scans the box sticker with a phone or
tablet. Odoo opens that order, checks every station is done and the invoice is
paid, and marks it Dispatched in one tap."*

Everything here goes over HTTP, because what is being built is a ROUTE that
CHANGES DATA and the questions worth asking are about who may call it and
when it refuses. A model test would prove the arithmetic and miss all of
that - the pickup slots cost a day exactly that way.

Three of his decisions are pinned, asked and answered 2026-10-28:

  * UNPAID BLOCKS, with no override;
  * AN OPEN STATION only warns, and can be gone past;
  * A DEALER ON ACCOUNT passes the payment check, because a Quick Order
    raises no invoice at the time and the rule would otherwise block every
    dealer collection there is.
"""

import re

from odoo import fields
from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class DispatchScanCase(HttpCase):

    PASSWORD = "aa-dispatch-password"

    def setUp(self):
        super().setUp()
        self.customer = self.env["res.partner"].create(
            {"name": "Hector the Fitter"})
        self.product = self.env["product.product"].create({
            "name": "A door part", "type": "consu", "is_storable": True,
            "list_price": 100.0})

        self.desk = self.env["res.users"].create({
            "name": "The dispatch desk",
            "login": "aa_dispatch_desk",
            "password": self.PASSWORD,
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("stock.group_stock_user").id])],
        })
        self.nosy = self.env["res.users"].create({
            "name": "Somebody else",
            "login": "aa_not_dispatch",
            "password": self.PASSWORD,
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })

    # --- fixtures ---------------------------------------------------------

    def _picking(self, invoiced=True, paid=True):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 1})],
        })
        order.action_confirm()

        if invoiced:
            invoice = order._create_invoices()
            invoice.action_post()

            if paid:
                self.env["account.payment.register"].with_context(
                    active_model="account.move", active_ids=invoice.ids
                ).create({
                    "payment_date": fields.Date.context_today(invoice),
                }).action_create_payments()

        # HIS WAREHOUSE DELIVERS IN TWO STEPS (`pick_ship`), so confirming an
        # order makes an INTERNAL pick and nothing else - the outgoing
        # delivery, which is the one the dispatch desk sees and the only kind
        # `action_aa_dispatched` will touch, appears once that pick is
        # validated. Which is the real flow: the shop builds it, then it is
        # ready at the door.
        pick = order.picking_ids.filtered(
            lambda p: p.picking_type_code == "internal")

        for move in pick.move_ids:
            move.quantity = move.product_uom_qty

        pick.button_validate()
        order.invalidate_recordset()

        picking = order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing")[:1]
        self.assertTrue(picking, "the order made no delivery")
        picking.action_assign()

        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        return order, picking

    def _url(self, picking):
        return "/dispatch/%d/%s" % (picking.id, picking._aa_dispatch_token())

    def _open(self, picking, login="aa_dispatch_desk"):
        self.authenticate(login, self.PASSWORD)

        return self.url_open(self._url(picking))

    def _tap(self, picking, login="aa_dispatch_desk"):
        """Press the button, as the page's own form does."""
        self.authenticate(login, self.PASSWORD)
        page = self.url_open(self._url(picking)).text
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)

        self.assertTrue(token, "the page offered no button to press")

        return self.url_open(self._url(picking) + "/go",
                             data={"csrf_token": token.group(1)})

    # --- the sentence he wrote --------------------------------------------

    def test_a_paid_order_is_dispatched_in_one_tap(self):
        """THE ONE THAT SETTLES IT."""
        _order, picking = self._picking()

        answer = self._tap(picking)

        self.assertEqual(answer.status_code, 200)
        self.assertIn("Dispatched", answer.text)
        self.assertTrue(picking.aa_dispatched_on, "nothing was recorded")
        self.assertEqual(picking.aa_dispatched_by, self.desk)
        self.assertEqual(picking.state, "done")

    def test_the_page_says_what_it_checked(self):
        _order, picking = self._picking()

        page = self._open(picking).text

        self.assertIn(picking.name, page)
        self.assertIn("Hector the Fitter", page)
        self.assertIn("Payment:", page)
        self.assertIn("Stations:", page)

    # --- unpaid blocks, and there is no way round it ----------------------

    def test_an_unpaid_order_cannot_be_dispatched(self):
        """HIS CALL: "money is not a thing for a judgement call at the
        counter." The button is dead and the page says why."""
        _order, picking = self._picking(paid=False)

        page = self._open(picking).text

        self.assertIn("NOT PAID", page)
        self.assertIn("Cannot dispatch", page)

    def test_the_route_refuses_an_unpaid_order_even_if_posted_to(self):
        """THE BUTTON IS NOT THE LOCK. The page can be open since this
        morning, the invoice can have been cancelled since, and a form can be
        posted to directly - so the bar is applied where it bites."""
        _paid, allowed = self._picking()
        _unpaid, refused = self._picking(paid=False)
        self.authenticate("aa_dispatch_desk", self.PASSWORD)

        # A REAL TOKEN, taken off the page of an order that IS payable. The
        # csrf token belongs to the session rather than to one form, so this
        # is exactly what somebody fiddling with the URL would have - and it
        # proves the PAYMENT check refuses, rather than proving csrf does.
        page = self.url_open(self._url(allowed)).text
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
        self.assertTrue(token, "could not get a session token to post with")

        answer = self.url_open(self._url(refused) + "/go",
                               data={"csrf_token": token.group(1)})

        self.assertEqual(answer.status_code, 200)
        self.assertFalse(refused.aa_dispatched_on,
                         "an unpaid order was dispatched by posting to it")
        self.assertEqual(refused.state, "assigned")
        self.assertIn("NOT PAID", answer.text)

    def test_an_order_with_no_invoice_at_all_is_not_paid(self):
        _order, picking = self._picking(invoiced=False)

        page = self._open(picking).text

        self.assertIn("no invoice has been raised", page)
        self.assertIn("Cannot dispatch", page)

    # --- a dealer on account passes --------------------------------------

    def test_a_dealer_on_account_may_collect(self):
        """A Quick Order charged to account raises NO invoice at the time, so
        "no paid invoice" would have blocked every dealer collection. He
        chose to let them through, saying ON ACCOUNT rather than UNPAID."""
        if "aa_order_on_account" not in self.env["res.partner"]._fields:
            self.skipTest("aa_dealer_orders is not installed here")

        self.customer.aa_order_on_account = True
        _order, picking = self._picking(invoiced=False)

        page = self._open(picking).text

        self.assertIn("On account", page)
        self.assertNotIn("Cannot dispatch", page)

    # --- an open station warns but does not stop --------------------------

    def test_an_open_station_is_a_warning_and_not_a_bar(self):
        """His call the other way round: a foreman can see the box is packed
        and the system is sometimes behind the shop."""
        order, picking = self._picking()
        self.env["mrp.production"].create({
            "product_id": self.product.id,
            "product_qty": 1.0,
            "origin": order.name,
        })

        page = self._open(picking).text

        self.assertIn("still open", page)
        self.assertNotIn("Cannot dispatch", page)
        self.assertIn("Mark Dispatched", page)

    def test_an_open_station_asks_before_it_goes(self):
        """The second tap. A confirm is the whole difference between a
        warning and a bar."""
        order, picking = self._picking()
        self.env["mrp.production"].create({
            "product_id": self.product.id, "product_qty": 1.0,
            "origin": order.name})

        page = self._open(picking).text

        self.assertIn("Dispatch anyway?", page)

    # --- who may do it ----------------------------------------------------

    def test_a_portal_user_is_turned_away(self):
        """THE ONE REAL DIFFERENCE FROM THE BOX STICKER. That link is public
        because reading a door's figures is harmless; this one marks an order
        collected, and a public version would let anybody who photographed a
        form empty the dispatch list."""
        _order, picking = self._picking()

        page = self._open(picking, login="aa_not_dispatch").text

        self.assertIn("for the dispatch desk", page)
        self.assertNotIn("Mark Dispatched", page)

    def test_a_portal_user_cannot_post_to_it_either(self):
        _order, picking = self._picking()
        self.authenticate("aa_not_dispatch", self.PASSWORD)

        self.url_open(self._url(picking) + "/go", data={})

        self.assertFalse(picking.aa_dispatched_on)

    def test_a_wrong_token_opens_nothing(self):
        """A URL that is only an id is a URL somebody edits."""
        _order, picking = self._picking()
        self.authenticate("aa_dispatch_desk", self.PASSWORD)

        answer = self.url_open("/dispatch/%d/%s" % (picking.id, "0" * 24))

        self.assertEqual(answer.status_code, 404)

    def test_one_transfers_token_does_not_open_another(self):
        _one, first = self._picking()
        _two, second = self._picking()
        self.authenticate("aa_dispatch_desk", self.PASSWORD)

        answer = self.url_open(
            "/dispatch/%d/%s" % (second.id, first._aa_dispatch_token()))

        self.assertEqual(answer.status_code, 404)

    # --- scanned twice ----------------------------------------------------

    def test_scanning_it_again_says_so_rather_than_failing(self):
        """Somebody scans the same sheet twice. That is an answer, not an
        error, and certainly not a second dispatch."""
        _order, picking = self._picking()
        self._tap(picking)
        first_time = picking.aa_dispatched_on

        page = self._open(picking).text

        self.assertIn("Dispatched by", page)
        self.assertEqual(picking.aa_dispatched_on, first_time)

    # --- the QR on the paper ----------------------------------------------

    def test_both_printed_forms_carry_the_qr(self):
        """Asked which form should carry it, he said BOTH - whichever sheet
        is in somebody's hand at the counter is the one they scan."""
        _order, picking = self._picking()
        reports = ("work_order_sheet.report_work_order_sheet",
                   "work_order_sheet.report_delivery_confirmation")

        for report in reports:
            html = self.env["ir.actions.report"]._render_qweb_html(
                report, picking.ids)[0].decode()

            self.assertIn("barcode_type=QR", html, report)
            self.assertIn("SCAN TO DISPATCH", html, report)

    def test_the_qr_holds_this_transfers_own_link(self):
        _order, picking = self._picking()

        self.assertIn("/dispatch/%d/" % picking.id, picking._aa_dispatch_url())
        self.assertIn(picking._aa_dispatch_token(), picking._aa_dispatch_url())

    def test_the_token_is_the_same_tomorrow(self):
        """DERIVED, NOT STORED: a form printed today still scans next week."""
        _order, picking = self._picking()

        self.assertEqual(picking._aa_dispatch_token(),
                         picking._aa_dispatch_token())
