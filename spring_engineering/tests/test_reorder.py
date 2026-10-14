import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestReorderAPreviousOrder(HttpCase):
    """Choose a previous order in the cart and have all of it back.

    Odoo's Quick Reorder offers the LINES of recent orders one at a time, and
    its button is disabled whenever that list is empty - which is why it read
    as a button that does nothing. This is the other shape: the orders
    themselves.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.admin = self.env["res.users"].browse(2)
        self.website = self.env["website"].search([], limit=1)
        self.hinge = self.env["product.product"].create({
            "name": "Reorder Probe Hinge", "type": "consu", "list_price": 4.0,
            "is_published": True, "sale_ok": True})
        self.roller = self.env["product.product"].create({
            "name": "Reorder Probe Roller", "type": "consu", "list_price": 9.0,
            "is_published": True, "sale_ok": True})

    def _past_order(self, website=None, state="sale"):
        order = self.env["sale.order"].create({
            "partner_id": self.admin.partner_id.id,
            "website_id": (website or self.website).id if website is not False else False,
            "order_line": [
                (0, 0, {"product_id": self.hinge.id, "product_uom_qty": 4}),
                (0, 0, {"product_id": self.roller.id, "product_uom_qty": 2}),
            ],
        })
        order.action_confirm()

        if state == "done":
            order.action_lock()

        return order

    def _cart(self):
        return self.env["sale.order"].search(
            [("partner_id", "=", self.admin.partner_id.id),
             ("state", "=", "draft")], order="id desc", limit=1)

    def _panel(self, page):
        """Just the reorder panel. The cart page carries data-order-id on its
        own markup too, so a search of the whole page answers about the wrong
        thing - which it did, and said a draft cart was being offered when it
        was not."""
        start = page.find("o_aa_reorder_orders")

        return page[start:] if start >= 0 else ""

    def _reorder(self, order):
        return self.url_open(
            "/my/orders/reorder",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"order_id": order.id}}),
            headers={"Content-Type": "application/json"}).json()

    # --- which orders are offered ---------------------------------------------

    def test_the_cart_offers_the_customers_finished_orders(self):
        order = self._past_order()
        self.authenticate("admin", "admin")
        page = self.url_open("/shop/cart").text

        panel = self._panel(page)
        self.assertIn("Order it all again", page)
        self.assertIn(order.name, panel)
        self.assertIn('data-order-id="%s"' % order.id, panel)

    def test_a_locked_order_is_still_one_you_bought(self):
        """A locked order does not sit in a state of its own in this version -
        it stays confirmed and carries a flag - so it is offered like any
        other. Asserted because an earlier draft of the domain asked for a
        'done' state that no sale order can be in."""
        order = self._past_order(state="done")
        self.assertEqual(order.state, "sale")
        self.assertTrue(order.locked)
        self.authenticate("admin", "admin")

        self.assertIn(order.name, self._panel(self.url_open("/shop/cart").text))

    def test_an_order_taken_over_the_phone_is_offered_too(self):
        """Odoo filters its history to orders placed on this website, which
        hides every one the office entered in the back office."""
        order = self._past_order(website=False)
        self.assertFalse(order.website_id)
        self.authenticate("admin", "admin")

        self.assertIn(order.name, self._panel(self.url_open("/shop/cart").text))

    def test_a_draft_cart_is_not_a_previous_order(self):
        self.authenticate("admin", "admin")
        self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": self.hinge.product_tmpl_id.id,
                "product_id": self.hinge.id, "quantity": 1}}),
            headers={"Content-Type": "application/json"})
        cart = self._cart()

        self.assertTrue(cart, "nothing in the cart to test with")
        panel = self._panel(self.url_open("/shop/cart").text)
        self.assertNotIn('data-order-id="%s"' % cart.id, panel)

    def test_somebody_elses_order_is_not_offered(self):
        other = self.env["res.partner"].create({"name": "Another Customer"})
        order = self.env["sale.order"].create({
            "partner_id": other.id,
            "order_line": [(0, 0, {"product_id": self.hinge.id,
                                   "product_uom_qty": 1})]})
        order.action_confirm()
        self.authenticate("admin", "admin")

        self.assertNotIn(order.name, self._panel(self.url_open("/shop/cart").text))

    def test_a_signed_out_visitor_is_offered_nothing(self):
        self._past_order()
        page = self.url_open("/shop/cart").text

        self.assertNotIn("Order it all again", page)

    # --- and what pressing Reorder does ---------------------------------------

    def test_reordering_puts_every_line_in_the_cart(self):
        order = self._past_order()
        self.authenticate("admin", "admin")

        self._reorder(order)
        cart = self._cart()

        self.assertEqual(
            {(line.product_id, line.product_uom_qty) for line in cart.order_line},
            {(self.hinge, 4.0), (self.roller, 2.0)})

    def test_reordering_twice_does_not_lose_the_first_one(self):
        """Odoo adds to what is in the cart rather than replacing it, which is
        what a customer building an order expects."""
        order = self._past_order()
        self.authenticate("admin", "admin")

        self._reorder(order)
        self._reorder(order)
        cart = self._cart()

        self.assertEqual(
            {line.product_id: line.product_uom_qty for line in cart.order_line},
            {self.hinge: 8.0, self.roller: 4.0})
