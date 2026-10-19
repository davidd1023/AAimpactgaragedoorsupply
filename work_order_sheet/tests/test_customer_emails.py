"""EVERY EMAIL THE CUSTOMER RECEIVES.

The owner, 2026-10-19: the order confirmation, the invoice, "ready for pickup"
and the cancellation should each be in English and carry the AA Impact logo,
the Medley warehouse address, the pickup hours and the W/O number. "These
emails currently use Odoo's generic templates."

So each of the four is RENDERED here and read, rather than trusted because the
XML parses. All four end with one shared block, and the test that matters most
is the one that renders every one of them and finds all four things in each.
"""

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

FOUR = [
    ("sale.mail_template_sale_confirmation", "order"),
    ("account.email_template_edi_invoice", "invoice"),
    ("work_order_sheet.mail_template_order_ready", "picking"),
    ("work_order_sheet.mail_template_order_cancelled", "order"),
]


@tagged("post_install", "-at_install")
class CustomerEmailsCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.write({
            "street": "9753 NW 91st Ct",
            "city": "Medley",
            "zip": "33178",
            "phone": "+1 786-238-7640",
            "email": "office@aaigd.com",
        })
        self.customer = self.env["res.partner"].create({
            "name": "Hector the Fitter", "email": "hector@example.com"})
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 100.0})
        self.order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 2})],
        })
        self.order.action_confirm()

    def _invoice(self):
        self.order._create_invoices()
        invoice = self.order.invoice_ids[:1]
        invoice.action_post()

        return invoice

    def _delivery(self):
        picking = self.order.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing")[:1]

        if not picking:
            # Two-step warehouse: the delivery appears when the pick is done.
            for step in self.order.picking_ids:
                self.env["stock.quant"]._update_available_quantity(
                    self.product, step.location_id, 10.0)
                step.action_assign()

                for move in step.move_ids:
                    move.quantity = move.product_uom_qty
                    move.picked = True

                step.button_validate()

            self.order.invalidate_recordset()
            picking = self.order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == "outgoing")[:1]

        self.assertTrue(picking, "the order has no delivery")

        return picking

    def _record(self, kind):
        return {"order": lambda: self.order,
                "invoice": self._invoice,
                "picking": self._delivery}[kind]()

    def _render(self, template_ref, record):
        template = self.env.ref(template_ref)
        rendered = template._generate_template(
            [record.id], ("subject", "body_html", "email_from"))[record.id]

        return rendered["subject"], rendered["body_html"], rendered["email_from"]

    # --- the four things, in all four emails ---------------------------------

    def test_every_customer_email_carries_all_four(self):
        """THE WHOLE INSTRUCTION, in one test: logo, Medley address, pickup
        hours and the W/O number, in each of the four."""
        self.assertTrue(self.order.aa_wo_number, "the order has no W/O number")

        for template_ref, kind in FOUR:
            record = self._record(kind)
            _subject, body, _sender = self._render(template_ref, record)

            with self.subTest(template=template_ref):
                self.assertIn("/web/image/res.company/", body, "no logo")
                self.assertIn("9753 NW 91st Ct", body, "no address")
                self.assertIn("Medley", body, "no town")
                self.assertIn("8:00 AM to 4:30 PM", body, "no pickup hours")
                self.assertIn(self.order.aa_wo_number, body, "no W/O number")

    def test_the_number_does_not_say_its_own_label_twice(self):
        """THE NUMBER CARRIES ITS OWN LABEL. The sequence prints "W/O #202",
        so a template that put "W/O #" in front of it read "W/O #W/O #202" -
        which it did, in the subject and twice in the body, until a render was
        read rather than asserted at."""
        for template_ref, kind in FOUR:
            record = self._record(kind)
            subject, body, _sender = self._render(template_ref, record)

            with self.subTest(template=template_ref):
                self.assertNotIn("W/O #W/O", subject)
                self.assertNotIn("W/O #W/O", body)
                self.assertIn("W/O #", body, "the label is gone altogether")

    def test_the_w_o_number_is_in_every_subject_too(self):
        """So a customer scanning a mailbox can match it without opening
        anything."""
        for template_ref, kind in FOUR:
            record = self._record(kind)
            subject, _body, _sender = self._render(template_ref, record)

            with self.subTest(template=template_ref):
                self.assertIn(self.order.aa_wo_number, subject)

    def test_all_four_are_in_english(self):
        """Asked for plainly, and worth pinning: Spanish is installed on this
        database, so a customer whose contact is set to it would otherwise get
        a half-translated email."""
        for template_ref, _kind in FOUR:
            with self.subTest(template=template_ref):
                self.assertEqual(self.env.ref(template_ref).lang, "en_US")

    def test_all_four_come_from_one_mailbox(self):
        """A customer who gets four emails from a shop should get them from
        one address, and a reply to any of them should land there."""
        self.env["ir.config_parameter"].sudo().set_param(
            "work_order_sheet.ready_email_from", "sales@aaigd.com")

        for template_ref, kind in FOUR:
            record = self._record(kind)
            _subject, _body, sender = self._render(template_ref, record)

            with self.subTest(template=template_ref):
                self.assertIn("sales@aaigd.com", sender or "")

    def test_the_hours_are_a_setting_not_a_sentence_in_the_html(self):
        """Changed in Inventory > Settings, and the emails follow."""
        self.company.aa_pickup_hours = "Weekdays 7 to 7, Saturday mornings"
        _subject, body, _sender = self._render(
            "sale.mail_template_sale_confirmation", self.order)

        self.assertIn("Weekdays 7 to 7", body)
        self.assertNotIn("4:30", body)

    # --- each one says its own thing -----------------------------------------

    def test_the_confirmation_says_the_order_is_in(self):
        subject, body, _sender = self._render(
            "sale.mail_template_sale_confirmation", self.order)

        self.assertIn("is confirmed", subject)
        self.assertIn(self.order.name, body)
        self.assertIn("ready to collect", body)
        self.assertIn("Your Orders", body, "no link to follow it")

    def test_the_invoice_email_names_the_invoice_and_the_order(self):
        invoice = self._invoice()
        subject, body, _sender = self._render(
            "account.email_template_edi_invoice", invoice)

        self.assertIn(invoice.name, subject)
        self.assertIn(invoice.name, body)
        self.assertIn(self.order.aa_wo_number, body)

    def test_an_invoice_for_two_orders_names_both(self):
        """A customer reading only the first would ring up about the other."""
        second = self.order.copy()
        second.action_confirm()
        (self.order | second)._create_invoices()
        invoice = self.env["account.move"].search(
            [("invoice_origin", "!=", False)], order="id desc", limit=1)
        numbers = invoice._aa_email_wo_number()

        if second.aa_wo_number and second.aa_wo_number in (invoice.invoice_origin or ""):
            self.assertIn(second.aa_wo_number, numbers)

    def test_the_ready_email_is_still_short(self):
        """"we dont need to give them too much detail just that their order is
        ready" - the letterhead is not detail about the order."""
        picking = self._delivery()
        _subject, body, _sender = self._render(
            "work_order_sheet.mail_template_order_ready", picking)

        self.assertIn("is ready for pickup", body)
        self.assertNotIn("A thing", body, "it listed the contents")

    def test_the_cancellation_email_exists_at_all(self):
        """THERE WAS NONE. Odoo does not send one and the Cancel & Refund
        procedure did not either, so a customer whose paid order was cancelled
        heard nothing."""
        subject, body, _sender = self._render(
            "work_order_sheet.mail_template_order_cancelled", self.order)

        self.assertIn("has been cancelled", subject)
        self.assertIn("has been cancelled", body)

    def test_the_cancellation_says_nothing_was_charged_when_nothing_was(self):
        _subject, body, _sender = self._render(
            "work_order_sheet.mail_template_order_cancelled", self.order)

        self.assertIn("nothing to refund", body)

    def test_cancelling_an_order_actually_sends_it(self):
        """The wizard sends it, which is the half that was missing."""
        wizard = self.env["aa.order.cancel"].create({"order_id": self.order.id})
        self.env.user.group_ids = [
            (4, self.env.ref("sales_team.group_sale_manager").id)]
        wizard.action_cancel_and_refund()

        mails = self.env["mail.mail"].search(
            [("model", "=", "sale.order"), ("res_id", "=", self.order.id)])
        self.assertTrue(mails, "the customer was not told it was cancelled")
        self.assertIn("cancelled", (mails[0].subject or "").lower())

    # --- and nothing generic left --------------------------------------------

    def test_the_w_o_number_is_found_on_each_kind_of_record(self):
        """It lives on the order; the invoice reaches it through its lines and
        the delivery through the order it belongs to."""
        self.assertEqual(self.order._aa_email_wo_number(),
                         self.order.aa_wo_number)
        self.assertEqual(self._invoice()._aa_email_wo_number(),
                         self.order.aa_wo_number)
        self.assertEqual(self._delivery()._aa_email_wo_number(),
                         self.order.aa_wo_number)

    def test_an_order_with_no_w_o_number_still_renders(self):
        """An order from before the W/O number existed, or a quotation that
        was never confirmed: the line is left out rather than printed empty."""
        self.order.aa_wo_number = False
        subject, body, _sender = self._render(
            "sale.mail_template_sale_confirmation", self.order)

        self.assertNotIn("W/O #", subject)
        self.assertNotIn("W/O #", body)
        self.assertIn("9753 NW 91st Ct", body, "the rest still prints")
