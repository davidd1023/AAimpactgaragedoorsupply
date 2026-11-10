"""ADMIN ONLY: ADD A HARDWARE BOX, TRACKS OR SPRINGS TO A DEALER ORDER ALREADY PLACED.

Owner, 2026-11-02, about W/O #332: an admin-only button to add tracks, or
springs when there are none, or the hardware box - reflected in the order's
cost, and only for AA Impact's on-account orders, never on a purchase. See
add_parts.py for the three decisions he made.
"""
import json

from odoo import Command
from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class AddPartsCase(HttpCase):

    def setUp(self):
        super().setUp()
        self.dealer = self.env["res.partner"].create({
            "name": "Add Parts Dealer", "is_company": True, "aa_order_on_account": True})
        self.walk_in = self.env["res.partner"].create({"name": "Add Parts Walk-in"})
        self.widget = self.env["product.product"].create({
            "name": "Add Parts Widget", "type": "consu", "list_price": 100.0,
            "invoice_policy": "order"})
        self.kit = self.env["product.template"].create({
            "name": "AA-1800 Add Parts Kit", "type": "consu", "list_price": 500.0,
            "invoice_policy": "order", "aa_dealer_quick_order": True})

    def _order(self, partner=None, lines=None):
        order = self.env["sale.order"].create({
            "partner_id": (partner or self.dealer).id,
            "order_line": lines or [Command.create({"product_id": self.widget.id})],
        })
        order.action_confirm()
        return order

    # --- who sees the buttons ---------------------------------------------------

    def test_admin_on_account_order_shows_the_buttons(self):
        order = self._order()
        self.assertTrue(order.aa_add_parts_allowed)
        self.assertTrue(order.aa_needs_box, "no kit on the order")
        self.assertTrue(order.aa_needs_tracks, "no track on the order")
        self.assertTrue(order.aa_needs_springs, "no spring on the order")

    def test_not_for_a_customer_who_is_not_on_account(self):
        order = self._order(self.walk_in)
        self.assertFalse(order.aa_add_parts_allowed)
        self.assertFalse(order.aa_needs_tracks)

    def test_not_for_a_non_admin(self):
        order = self._order()
        clerk = self.env["res.users"].create({
            "name": "Add Parts Clerk", "login": "add_parts_clerk",
            "group_ids": [Command.set([self.env.ref("sales_team.group_sale_salesman").id])]})
        self.assertFalse(order.with_user(clerk).aa_add_parts_allowed)
        self.assertFalse(order.with_user(clerk).aa_needs_tracks)

    def test_not_for_a_quotation(self):
        order = self.env["sale.order"].create({
            "partner_id": self.dealer.id,
            "order_line": [Command.create({"product_id": self.widget.id})]})
        self.assertFalse(order.aa_add_parts_allowed)

    def test_not_for_a_purchase_paid_at_checkout(self):
        """"si fuera una compra no debe salir" - a card payment hides it."""
        order = self._order()
        provider = self.env["payment.provider"].search([], limit=1)
        method = provider.payment_method_ids[:1] or self.env["payment.method"].search([], limit=1)
        if not provider or not method:
            self.skipTest("no payment provider in this database")
        self.env["payment.transaction"].create({
            "provider_id": provider.id, "payment_method_id": method.id,
            "amount": order.amount_total, "currency_id": order.currency_id.id,
            "partner_id": self.walk_in.id, "reference": "ADDPARTS-TX", "state": "done",
            "sale_order_ids": [Command.set(order.ids)]})
        order.invalidate_recordset()
        self.assertFalse(order.aa_add_parts_allowed)

    def test_kit_hides_the_box_button(self):
        order = self._order(lines=[Command.create({"product_id": self.kit.product_variant_id.id})])
        self.assertFalse(order.aa_needs_box)
        self.assertTrue(order.aa_needs_tracks)

    def test_custom_track_counts_as_tracks(self):
        custom = self.env.ref("aa_dealer_orders.product_custom_track").product_variant_id
        order = self._order(lines=[Command.create({"product_id": custom.id, "price_unit": 211.54})])
        self.assertFalse(order.aa_needs_tracks)

    def test_the_custom_track_is_not_read_as_a_prepared_track(self):
        """Its name must not trip _aa_track_facts, or it would raise a Track Prep job."""
        custom = self.env.ref("aa_dealer_orders.product_custom_track").product_variant_id
        self.assertFalse(custom._aa_track_facts())
        self.assertEqual(custom.type, "service")

    # --- the doors the page is filled with --------------------------------------

    def test_door_rows_read_the_kit_line_note(self):
        """W/O #332's kit line, word for word: the size and weight are only in the note."""
        order = self._order(lines=[Command.create({
            "product_id": self.kit.product_variant_id.id, "product_uom_qty": 3,
            "aa_track_type": "3-15R", "aa_lift_type": "standard", "aa_drum": "D525-216",
            "name": ("AA-1800 Hardware Kit\nTrack: 3\" 15R | Lift: Standard | Drum: D525-216 | "
                     "Door: 1027 - ROSEN 5224 - 18x11 | W 216\" x H 132\" | 1515 lb | "
                     "Tracks: no prepared 3\" horizontal for 144\" - AA prepares it")})])
        [row] = order._aa_door_rows()
        self.assertEqual(row["width_in"], 216)
        self.assertEqual(row["height_in"], 132)
        self.assertEqual(row["weight"], 1515)
        self.assertEqual(row["qty"], 3)
        self.assertEqual(row["tag"], "1027 - ROSEN 5224 - 18x11")
        self.assertEqual(row["track_type"], "3-15R")
        self.assertEqual(row["drum"], "D525-216")

    # --- the page and the routes refuse outsiders --------------------------------

    def test_add_page_is_refused_to_a_portal_dealer(self):
        order = self._order()
        user = self.env["res.users"].create({
            "name": "Add Parts Portal", "login": "add_parts_portal", "password": "add_parts_portal",
            "partner_id": self.dealer.id,
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])]})
        self.authenticate(user.login, "add_parts_portal")
        page = self.url_open(f"/dealer/order/add/{order.id}?part=tracks").text
        self.assertIn("only available to AA Impact preferred dealers", page)
        res = self.url_open(
            f"/dealer/order/add/{order.id}/submit",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"part": "tracks", "lines": [{}]}}),
            headers={"Content-Type": "application/json"}).json()
        self.assertIn("administrator", res["result"]["error"])

    def test_add_page_opens_for_admin_filled_with_the_doors(self):
        order = self._order(lines=[Command.create({
            "product_id": self.kit.product_variant_id.id,
            "name": "Kit\nDoor: Smith | W 192\" x H 96\" | 300 lb"})])
        self.authenticate("admin", "admin")
        page = self.url_open(f"/dealer/order/add/{order.id}?part=tracks").text
        self.assertIn('data-add-part="tracks"', page)
        self.assertIn("Smith", page)
        self.assertIn("Add Tracks to", page)

    # --- the invoice is redone ---------------------------------------------------

    def test_unpaid_invoice_is_redone_under_the_same_number(self):
        order = self._order()
        invoice = order._create_invoices()
        invoice.action_post()
        number, before = invoice.name, invoice.amount_untaxed
        line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.widget.id, "price_unit": 50.0})
        note = order._aa_reinvoice(line)
        self.assertIn(number, note)
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.name, number)
        self.assertAlmostEqual(invoice.amount_untaxed, before + 50.0)
        self.assertEqual(len(order.invoice_ids), 1)
        self.assertEqual(line.qty_invoiced, 1)

    def test_never_invoiced_order_is_left_alone(self):
        order = self._order()
        line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.widget.id, "price_unit": 50.0})
        self.assertEqual(order._aa_reinvoice(line), "")
        self.assertFalse(order.invoice_ids)

    # --- removing a part (owner, 2026-11-02, on the Shop Floor) -------------------

    def test_remove_tracks_zeroes_the_line_and_redoes_the_invoice(self):
        custom = self.env.ref("aa_dealer_orders.product_custom_track").product_variant_id
        order = self._order(lines=[
            Command.create({"product_id": self.widget.id}),
            Command.create({"product_id": custom.id, "price_unit": 211.54})])
        invoice = order._create_invoices()
        invoice.action_post()
        number = invoice.name
        self.assertFalse(order.aa_needs_tracks)
        message = order.aa_remove_part("tracks")
        self.assertIn("Tracks removed", message)
        track_line = order.order_line.filtered(lambda l: l.product_id == custom)
        self.assertEqual(track_line.product_uom_qty, 0)
        self.assertTrue(order.aa_needs_tracks, "the Add button comes back")
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.name, number)
        # NOT AN ABSOLUTE FIGURE. This asserted 100.0 - the widget's list
        # price - and arrived as 90.0 on every development build, because
        # THE DEV DATABASE CARRIES A DEMO PRICELIST TAKING 10% OFF
        # EVERYTHING (CLAUDE.md records the same trap costing a day on the
        # shop-grid price work). It passes on staging and Prod, which are
        # copies of production and have no such pricelist, so the feature
        # was never broken - only the test was environment-dependent, and
        # it would have failed for whoever next merged.
        #
        # The sibling tests here escape it by setting `price_unit` on their
        # lines by hand; this one lets the product's list price flow through
        # the order, which is where a pricelist applies.
        #
        # What the test MEANS is that the track is off the redone invoice and
        # the widget alone is left, and that survives any pricelist.
        self.assertEqual(
            invoice.invoice_line_ids.product_id, self.widget,
            "the redone invoice should carry the widget and nothing else")
        self.assertNotIn(custom, invoice.invoice_line_ids.product_id,
                         "the removed track must be off the invoice")

    def test_remove_something_not_there_is_refused(self):
        from odoo.exceptions import UserError
        order = self._order()
        with self.assertRaises(UserError):
            order.aa_remove_part("springs")

    def test_parts_board_lists_what_the_order_has(self):
        order = self._order(lines=[Command.create({"product_id": self.kit.product_variant_id.id})])
        board = order._aa_parts_board()
        has = {p["part"]: p["has"] for p in board["parts"]}
        self.assertEqual(has, {"box": True, "tracks": False, "springs": False})
        self.assertIsNone(self._order(self.walk_in)._aa_parts_board())

    def test_a_second_submit_adds_nothing(self):
        """Never charged twice: the part is already there, so the route refuses."""
        custom = self.env.ref("aa_dealer_orders.product_custom_track").product_variant_id
        order = self._order(lines=[Command.create({"product_id": custom.id, "price_unit": 211.54})])
        before = order.amount_untaxed
        self.authenticate("admin", "admin")
        res = self.url_open(
            f"/dealer/order/add/{order.id}/submit",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"part": "tracks", "lines": [{"template_id": 1}]}}),
            headers={"Content-Type": "application/json"}).json()
        self.assertIn("already on this order", res["result"]["error"])
        order.invalidate_recordset()
        self.assertEqual(order.amount_untaxed, before)
        self.assertFalse(order.transaction_ids, "adding never creates a payment")

    def test_adding_after_invoicing_does_not_rebill_the_old_lines(self):
        """The redone invoice carries each line once: old ones are not billed again."""
        order = self._order()
        invoice = order._create_invoices()
        invoice.action_post()
        line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.widget.id, "price_unit": 50.0})
        order._aa_reinvoice(line)
        self.assertEqual(len(order.invoice_ids), 1)
        self.assertAlmostEqual(invoice.amount_untaxed, order.amount_untaxed)
        self.assertEqual(sorted(invoice.invoice_line_ids.mapped("quantity")), [1.0, 1.0])
