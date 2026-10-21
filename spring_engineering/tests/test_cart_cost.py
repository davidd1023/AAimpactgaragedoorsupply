import json
import re

from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCartCost(TransactionCase):
    """What the cart costs us, added up from the products' own Cost field.

    The figure is for staff. The sum is deliberately unclever - Cost times
    quantity, nothing inferred, no margin removed - so it is the same number
    somebody would get by opening every product in the cart one at a time,
    which is the number they are checking it against.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.partner = self.env["res.partner"].create({"name": "Cost Reader"})
        self.product = self.env["product.product"].create({
            "name": "Cost Probe Roller", "type": "consu",
            "list_price": 30.0, "standard_price": 11.0,
            "sale_ok": True, "is_published": True})

    def _cart(self, quantity=1, product=None):
        """A cart at a known price AND a known cost.

        PRICE IS SET BY HAND for the same reason the minimum-order tests set
        it: the demo pricelist takes 10% off, which has nothing to do with
        cost but makes every figure read strangely next to it.
        """
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})
        order.order_line = [(0, 0, {
            "product_id": (product or self.product).id,
            "product_uom_qty": quantity,
            "price_unit": 30.0, "discount": 0.0})]

        return order

    # --- the sum itself -------------------------------------------------------

    def test_the_cost_is_the_product_cost_times_the_quantity(self):
        self.assertEqual(self._cart(4)._aa_cart_cost(), {"cost": 44.0, "unpriced": 0})

    def test_an_empty_cart_costs_nothing_and_says_nothing_is_missing(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})

        self.assertEqual(order._aa_cart_cost(), {"cost": 0.0, "unpriced": 0})

    def test_every_line_is_counted_including_the_ones_the_cart_folds_away(self):
        """A fastener is hidden from the cart as a ROW, not from the order. It
        is picked, shipped and paid for, so it costs."""
        stud = self.env["product.product"].create({
            "name": "Cost Probe Stud", "type": "consu", "standard_price": 0.5,
            "sale_ok": True})
        order = self._cart(2)
        bracket = order.order_line[0]
        order.order_line = [(0, 0, {
            "product_id": stud.id, "product_uom_qty": 4,
            "price_unit": 1.0, "discount": 0.0,
            "track_prep_role": "stud", "track_prep_parent_id": bracket.id})]

        self.assertFalse(order.order_line[-1]._show_in_cart(),
                         "the fixture wants a line the cart folds away")
        self.assertEqual(order._aa_cart_cost()["cost"], 24.0)

    def test_the_cost_is_rounded_like_money(self):
        """Three at $11.11 is $33.329999999999998 in floating point, and a
        cart that prints a cost of $33.33 should hold $33.33."""
        self.product.standard_price = 11.11

        self.assertEqual(self._cart(3)._aa_cart_cost()["cost"], 33.33)

    # --- what does not count --------------------------------------------------

    def test_delivery_is_not_a_product_with_a_missing_cost(self):
        order = self._cart(1)
        order.order_line = [(0, 0, {
            "product_id": self.product.id, "product_uom_qty": 1,
            "price_unit": 80.0, "discount": 0.0,
            "is_delivery": True, "name": "Delivery"})]

        self.assertEqual(order._aa_cart_cost(), {"cost": 11.0, "unpriced": 0})

    def test_a_note_line_counts_for_nothing(self):
        order = self._cart(1)
        order.order_line = [(0, 0, {
            "name": "Please deliver round the back", "display_type": "line_note"})]

        self.assertEqual(order._aa_cart_cost(), {"cost": 11.0, "unpriced": 0})

    # --- the lines that have no cost to give ---------------------------------

    def test_a_product_with_no_cost_adds_nothing_and_is_counted(self):
        """SAID OUT LOUD, because a total that is quietly short reads like a
        real cost and is not one. A custom spring is priced as it is added to
        the cart and has no Cost field of its own."""
        spring = self.env["product.product"].create({
            "name": "Cost Probe Spring", "type": "consu", "standard_price": 0.0,
            "sale_ok": True})
        order = self._cart(2)
        order.order_line = [(0, 0, {
            "product_id": spring.id, "product_uom_qty": 1,
            "price_unit": 410.0, "discount": 0.0})]

        self.assertEqual(order._aa_cart_cost(), {"cost": 22.0, "unpriced": 1})

    def test_a_kit_header_is_not_reported_as_uncosted(self):
        """A custom kit's own line lists at nothing on purpose - the parts
        carry the money, each on its own line - so there is no Cost field for
        anybody to go looking for."""
        header = self.env["product.product"].create({
            "name": "Cost Probe Kit", "type": "consu", "list_price": 0.0,
            "standard_price": 0.0, "sale_ok": True})
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})
        order.order_line = [(0, 0, {
            "product_id": header.id, "product_uom_qty": 1,
            "price_unit": 0.0, "discount": 0.0})]
        kit_line = order.order_line[0]
        order.order_line = [(0, 0, {
            "product_id": self.product.id, "product_uom_qty": 3,
            "price_unit": 30.0, "discount": 0.0,
            "linked_line_id": kit_line.id})]

        self.assertEqual(order._aa_cart_cost(), {"cost": 33.0, "unpriced": 0})

    # --- units ----------------------------------------------------------------

    def test_a_line_sold_by_the_dozen_costs_twelve_pieces(self):
        """Cost is held per the product's OWN unit. A line sold by the dozen
        against a cost held per piece would be out by a factor of twelve."""
        order = self._cart(2)
        order.order_line.product_uom_id = self.env.ref("uom.product_uom_dozen")

        self.assertEqual(order._aa_cart_cost()["cost"], 264.0)

    # --- who it is for --------------------------------------------------------

    def test_a_customer_is_given_no_figure_at_all(self):
        """NONE, NOT ZERO. The template renders nothing for a customer - no
        label, no empty cell, no hint the row exists."""
        public = self.website.user_id

        self.assertFalse(public._is_internal(), "the fixture wants a shopper")
        self.assertIsNone(self._cart(4).with_user(public.id)._aa_cart_cost())

    def test_a_portal_customer_is_given_no_figure_either(self):
        portal = self.env["res.users"].create({
            "name": "Portal Shopper", "login": "cost_portal_shopper",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])]})

        self.assertFalse(portal._is_internal())
        self.assertIsNone(self._cart(4).with_user(portal.id)._aa_cart_cost())

    def test_an_employee_is_given_the_figure(self):
        employee = self.env["res.users"].create({
            "name": "Counter Staff", "login": "cost_counter_staff",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})

        self.assertTrue(employee._is_internal())
        self.assertEqual(
            self._cart(4).with_user(employee.id)._aa_cart_cost()["cost"], 44.0)


@tagged("post_install", "-at_install")
class TestCartCostOnThePage(HttpCase):
    """What is on the page, and - the point of the whole thing - whose page."""

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        # The row sits under the Total, and a cart held back by the shop's
        # minimum is a different test's subject.
        self.env["website"].search([]).write({"aa_minimum_order_amount": 0.0})
        self.product = self.env["product.product"].create({
            "name": "Cost Page Roller", "type": "consu",
            "list_price": 30.0, "standard_price": 11.0,
            "sale_ok": True, "is_published": True})
        self.product.product_tmpl_id.is_published = True

    def _add(self, quantity):
        return self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": self.product.product_tmpl_id.id,
                "product_id": self.product.id, "quantity": quantity}}),
            headers={"Content-Type": "application/json"})

    def _row(self, page):
        """The cost row, with its whitespace collapsed the way a browser
        collapses it - the sentence is built from several template nodes, so
        the source newlines between them are not what anybody reads."""
        hit = re.search(r"<tr[^>]*aa_cart_cost.*?</tr>", page, re.S)

        return re.sub(r"\s+", " ", hit.group(0)) if hit else ""

    def test_an_employee_sees_the_cost_under_the_total(self):
        self.authenticate("admin", "admin")
        self._add(4)
        row = self._row(self.url_open("/shop/cart").text)

        self.assertTrue(row, "no cost row on the cart page for an employee")
        self.assertIn("44.00", row, row)
        self.assertIn("staff only", row, row)

    def test_the_employee_sees_it_on_the_checkout_summary_too(self):
        """One template feeds the cart page and the summary card on every
        checkout and payment step, so the figure travels with the order."""
        self.authenticate("admin", "admin")
        self._add(4)
        row = self._row(self.url_open("/shop/checkout").text)

        self.assertTrue(row, "no cost row in the checkout summary")
        self.assertIn("44.00", row, row)

    def test_a_shopper_sees_no_cost_row_and_no_cost_figure(self):
        self._add(4)
        page = self.url_open("/shop/cart").text

        self.assertIn("Total", page, "the fixture did not reach a cart page")
        self.assertFalse(self._row(page), "the cost was shown to a customer")
        self.assertNotIn("staff only", page)
        self.assertNotIn("44.00", page, "a customer can read the cost off the page")

    def test_the_warning_names_how_many_lines_have_no_cost(self):
        uncosted = self.env["product.product"].create({
            "name": "Cost Page Spring", "type": "consu", "list_price": 410.0,
            "standard_price": 0.0, "sale_ok": True, "is_published": True})
        uncosted.product_tmpl_id.is_published = True
        self.authenticate("admin", "admin")
        self._add(4)
        self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": uncosted.product_tmpl_id.id,
                "product_id": uncosted.id, "quantity": 1}}),
            headers={"Content-Type": "application/json"})
        row = self._row(self.url_open("/shop/cart").text)

        self.assertIn("no cost set", row, row)
        self.assertIn("1 item has", row, row)
