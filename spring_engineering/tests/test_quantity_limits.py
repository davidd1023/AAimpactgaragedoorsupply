import re

from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHowMuchOfOneThingACartMayHold(TransactionCase):
    """The quantity box on a product page is a text field.

    Reported by the owner: a customer can ask for any number at all, can ask
    for minus one, and can type letters into it. The page should not allow
    the first two, but the page is not where it can be settled - anybody can
    post to the route without ever loading it.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.website.aa_maximum_line_quantity = 1000
        self.partner = self.env["res.partner"].create({"name": "Bulk Buyer"})
        self.product = self.env["product.product"].create({
            "name": "Quantity Probe Roller", "type": "consu",
            "list_price": 3.0, "sale_ok": True, "is_published": True})

    def _cart(self):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})

    def _qty(self, order):
        return sum(order.order_line.filtered(
            lambda line: line.product_id == self.product
        ).mapped("product_uom_qty"))

    # --- too many ------------------------------------------------------------

    def test_more_than_the_limit_is_cut_down_to_it(self):
        order = self._cart()

        answer = order._cart_add(product_id=self.product.id, quantity=5000)

        warning = answer.get("warning") or ""

        self.assertEqual(self._qty(order), 1000)
        self.assertTrue(warning, "the customer is not told what happened")
        self.assertIn("1,000" if "1,000" in warning else "1000", warning)

    def test_the_cart_page_cannot_raise_it_either(self):
        """The same box exists on the cart, so the rule lives where BOTH of
        them come through rather than on the page they came from."""
        order = self._cart()
        order._cart_add(product_id=self.product.id, quantity=5)
        line = order.order_line.filtered(
            lambda l: l.product_id == self.product)[:1]

        order._cart_update_line_quantity(line.id, 9999)

        self.assertEqual(self._qty(order), 1000)

    def test_exactly_the_limit_is_allowed(self):
        order = self._cart()

        order._cart_add(product_id=self.product.id, quantity=1000)

        self.assertEqual(self._qty(order), 1000)

    def test_no_limit_set_means_no_limit(self):
        self.website.aa_maximum_line_quantity = 0
        order = self._cart()

        order._cart_add(product_id=self.product.id, quantity=5000)

        self.assertEqual(self._qty(order), 5000)

    def test_an_order_with_no_website_is_not_capped(self):
        """The back office sells what it likes; this is a shop rule."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})

        order._cart_add(product_id=self.product.id, quantity=5000)

        self.assertEqual(self._qty(order), 5000)

    # --- fewer than one ------------------------------------------------------

    def test_minus_one_puts_one_in_the_cart(self):
        order = self._cart()

        order._cart_add(product_id=self.product.id, quantity=-1)

        self.assertEqual(self._qty(order), 1)

    def test_minus_one_does_not_empty_a_line_that_is_already_there(self):
        """THE SHARP EDGE. Odoo adds to an existing line by asking for "what
        it holds plus what you asked for", so minus one against a line of one
        came to zero - and zero means remove. Typing -1 deleted the line."""
        order = self._cart()
        order._cart_add(product_id=self.product.id, quantity=1)

        order._cart_add(product_id=self.product.id, quantity=-1)

        self.assertEqual(self._qty(order), 2, "the line was emptied, not added to")

    def test_zero_still_removes_a_line_from_the_cart(self):
        """The floor must not take away the one way out. Zero on the CART is
        how a line is removed, and Odoo never asks us about that one."""
        order = self._cart()
        order._cart_add(product_id=self.product.id, quantity=3)
        line = order.order_line.filtered(
            lambda l: l.product_id == self.product)[:1]

        order._cart_update_line_quantity(line.id, 0)

        self.assertFalse(line.exists(), "the customer cannot empty their cart")

    # --- not a number at all -------------------------------------------------

    def test_letters_do_not_reach_the_order(self):
        order = self._cart()

        order._cart_add(product_id=self.product.id, quantity="abc")

        self.assertEqual(self._qty(order), 1)

    def test_nothing_at_all_is_read_as_one(self):
        order = self._cart()

        order._cart_add(product_id=self.product.id, quantity=None)

        self.assertEqual(self._qty(order), 1)


@tagged("post_install", "-at_install")
class TestTheQuantityBoxItself(HttpCase):
    """What the page hands the customer, before the server has to correct it."""

    def setUp(self):
        super().setUp()
        self.env["website"].search([]).write({"aa_maximum_line_quantity": 1000})
        self.tmpl = self.env["product.template"].create({
            "name": "Quantity Box Roller", "type": "consu", "list_price": 4.0,
            "sale_ok": True, "is_published": True})

    def _add_qty_box(self):
        page = self.url_open(self.tmpl.website_url).text
        hit = re.search(r"<input[^>]*name=\"add_qty\"[^>]*>", page)

        return hit.group(0) if hit else ""

    def test_the_box_asks_for_a_number(self):
        box = self._add_qty_box()

        self.assertTrue(box, "no quantity box on the product page")
        self.assertIn('type="number"', box, box)
        self.assertIn('min="1"', box, box)
        self.assertIn('max="1000"', box, box)
        self.assertIn('inputmode="numeric"', box, box)

    def test_no_ceiling_is_offered_when_the_shop_sets_none(self):
        self.env["website"].search([]).write({"aa_maximum_line_quantity": 0})
        box = self._add_qty_box()

        self.assertIn('type="number"', box, box)
        self.assertNotIn("max=", box, "a limit was advertised that does not exist")
