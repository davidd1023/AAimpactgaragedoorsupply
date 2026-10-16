import json
import re

from odoo.exceptions import ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMinimumOrder(TransactionCase):
    """The least this shop will take as an order.

    Set in Website > Configuration > Settings. A cart worth less can be
    filled and changed as usual - it simply cannot be checked out.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.website.aa_minimum_order_amount = 500.0
        self.partner = self.env["res.partner"].create({"name": "Minimum Buyer"})
        self.product = self.env["product.product"].create({
            "name": "Minimum Probe Strut", "type": "consu",
            "list_price": 100.0, "sale_ok": True, "is_published": True})

    def _cart(self, quantity=1):
        """A cart at a known price.

        PRICE AND DISCOUNT ARE BOTH SET BY HAND. The demo pricelist takes 10%
        off, which is nothing to do with this rule but made every figure in
        here wrong by exactly that much.
        """
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})
        order.order_line = [(0, 0, {
            "product_id": self.product.id, "product_uom_qty": quantity,
            "price_unit": 100.0, "discount": 0.0})]

        return order

    # --- the rule itself ------------------------------------------------------

    def test_a_cart_under_the_minimum_is_not_ready(self):
        order = self._cart(3)

        self.assertEqual(order._aa_minimum_shortfall(), 200.0)
        self.assertFalse(order._is_cart_ready())

    def test_a_cart_over_the_minimum_is_ready(self):
        order = self._cart(6)

        self.assertFalse(order._aa_minimum_shortfall())
        self.assertTrue(order._is_cart_ready())

    def test_a_cart_of_exactly_the_minimum_is_ready(self):
        """TO THE CENT, IN MONEY RATHER THAN IN FLOATING POINT. A cart adding
        up to exactly the minimum can land a hundredth of a cent under it, and
        refusing that order - asking for $0.00 more - is indefensible."""
        order = self._cart(5)

        self.assertEqual(order._aa_amount_for_minimum(), 500.0)
        self.assertFalse(order._aa_minimum_shortfall())
        self.assertTrue(order._is_cart_ready())

    def test_no_minimum_set_means_no_rule(self):
        self.website.aa_minimum_order_amount = 0.0
        order = self._cart(1)

        self.assertFalse(order._aa_minimum_shortfall())
        self.assertTrue(order._is_cart_ready())

    def test_an_empty_cart_is_not_called_short(self):
        """It cannot be checked out either, but Odoo says that for itself and
        the cart page says so in words; "spend another $500" on an empty cart
        is a second message about the same nothing."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})

        self.assertFalse(order._aa_minimum_shortfall())
        self.assertFalse(order._is_cart_ready(), "an empty cart is still not ready")

    def test_a_back_office_order_has_no_minimum(self):
        """The rule belongs to the website. An order raised by the office is
        not a cart and must never be held up by a shop rule."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        order.order_line = [(0, 0, {
            "product_id": self.product.id, "product_uom_qty": 1})]

        self.assertFalse(order.website_id, "the fixture wants no website")
        self.assertFalse(order._aa_minimum_shortfall())

    # --- what counts towards it ----------------------------------------------

    def test_delivery_does_not_count_towards_the_minimum(self):
        """Letting the shipping charge make up the difference would mean a
        far-away customer qualifies with a smaller order than one next door."""
        order = self._cart(4)
        order.order_line = [(0, 0, {
            "product_id": self.product.id, "product_uom_qty": 1,
            "price_unit": 100.0, "discount": 0.0,
            "is_delivery": True, "name": "Delivery"})]

        self.assertEqual(order._aa_amount_for_minimum(), 400.0)
        self.assertEqual(order._aa_minimum_shortfall(), 100.0)

    def test_a_note_line_counts_for_nothing(self):
        order = self._cart(5)
        order.order_line = [(0, 0, {
            "name": "Please deliver round the back", "display_type": "line_note"})]

        self.assertEqual(order._aa_amount_for_minimum(), 500.0)
        self.assertFalse(order._aa_minimum_shortfall())

    # --- every door, not just the button -------------------------------------

    def test_paying_is_refused_and_says_why(self):
        order = self._cart(2)

        with self.assertRaises(ValidationError) as caught:
            order._check_cart_is_ready_to_be_paid()

        said = str(caught.exception)
        self.assertIn("500", said, said)
        self.assertIn("300", said, "it does not say how much is missing")

    def test_paying_is_allowed_once_the_minimum_is_met(self):
        """Past this rule it is Odoo's turn to object - about a shipping
        method, in this case - which is proof the minimum let it through."""
        order = self._cart(6)

        try:
            order._check_cart_is_ready_to_be_paid()
        except ValidationError as refused:
            self.assertNotIn("Orders start at", str(refused), str(refused))

    def test_express_checkout_is_closed_under_the_minimum(self):
        """Apple Pay and the like skip the cart's button entirely, so a
        minimum that only greyed that button out would be no minimum at all
        for anybody who used them."""
        self.assertFalse(self._cart(2)._allow_express_checkout())
        self.assertTrue(self._cart(6)._allow_express_checkout())


@tagged("post_install", "-at_install")
class TestMinimumOrderOnThePage(HttpCase):
    """What the customer sees, and what the URL does."""

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.env["website"].search([]).write({"aa_minimum_order_amount": 500.0})
        self.product = self.env["product.product"].create({
            "name": "Minimum Page Strut", "type": "consu",
            "list_price": 100.0, "sale_ok": True, "is_published": True})
        self.product.product_tmpl_id.is_published = True

    def _add(self, quantity):
        return self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": self.product.product_tmpl_id.id,
                "product_id": self.product.id, "quantity": quantity}}),
            headers={"Content-Type": "application/json"})

    def _button(self, page):
        hit = re.search(
            r"<a[^>]*name=\"website_sale_main_button\"[^>]*>", page)

        return hit.group(0) if hit else ""

    def _cart_record(self):
        return self.env["sale.order"].search(
            [("partner_id", "=", self.env["res.users"].browse(2).partner_id.id),
             ("website_id", "!=", False), ("state", "=", "draft")],
            order="id desc", limit=1)

    def test_the_cart_says_how_much_more_is_needed(self):
        self.authenticate("admin", "admin")
        self._add(2)
        page = self.url_open("/shop/cart").text
        short = self._cart_record()._aa_minimum_shortfall()

        self.assertTrue(short, "the fixture cart already qualifies")
        self.assertIn("aa_minimum_order_notice", page,
                      "the cart does not explain the grey button")
        self.assertIn("Orders start at", page)
        self.assertIn("%.2f" % short, page,
                      "it does not say how much is missing")

    def test_the_checkout_button_is_disabled_under_the_minimum(self):
        self.authenticate("admin", "admin")
        self._add(2)
        button = self._button(self.url_open("/shop/cart").text)

        self.assertTrue(button, "no checkout button on the cart page")
        self.assertIn("disabled", button, button)

    def test_the_notice_and_the_block_go_once_the_cart_qualifies(self):
        self.authenticate("admin", "admin")
        self._add(10)
        page = self.url_open("/shop/cart").text
        button = self._button(page)

        self.assertNotIn("aa_minimum_order_notice", page)
        self.assertNotIn("disabled", button, button)

    def test_typing_the_checkout_url_comes_straight_back_to_the_cart(self):
        """THE GREY BUTTON IS NOT THE RULE, it is how the rule looks. A
        customer with /shop/checkout in their history never presses it."""
        self.authenticate("admin", "admin")
        self._add(2)
        answer = self.url_open("/shop/checkout", allow_redirects=False)

        self.assertIn(answer.status_code, (301, 302, 303), answer.status_code)
        self.assertIn("/shop/cart", answer.headers.get("Location", ""))

    def test_a_qualifying_cart_may_go_to_the_checkout(self):
        self.authenticate("admin", "admin")
        self._add(10)
        answer = self.url_open("/shop/checkout")

        # FOLLOWED, AND THE END OF THE JOURNEY CHECKED. Asserting only that
        # the Location header does not say /shop/cart passes for a response
        # that has no Location at all - a 500 among them - so it proved the
        # cart was not bounced back and nothing whatever about the checkout.
        self.assertEqual(answer.status_code, 200, answer.status_code)
        self.assertNotIn("/shop/cart", answer.url,
                         "a cart over the minimum was sent back")
