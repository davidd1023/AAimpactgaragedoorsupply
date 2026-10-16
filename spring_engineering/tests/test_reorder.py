import json
import re

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

    def test_reordering_twice_leaves_one_copy_of_it(self):
        """THE RULE CHANGED HERE, deliberately. This used to assert that a
        second press ADDED a second copy, which is Odoo's behaviour and was
        this module's until the owner asked for the other one: reordering says
        order THIS again, not add this to whatever is in the cart. Pressing it
        twice now leaves what the order had, once."""
        order = self._past_order()
        self.authenticate("admin", "admin")

        self._reorder(order)
        self._reorder(order)
        cart = self._cart()

        self.assertEqual(
            {line.product_id: line.product_uom_qty for line in cart.order_line},
            {self.hinge: 4.0, self.roller: 2.0})


@tagged("post_install", "-at_install")
class TestReorderLeavesTheSyncsOwnParts(HttpCase):
    """What the fastener and track-prep sync makes is not the customer's.

    Those lines are recreated from the brackets as soon as the cart is
    rebuilt, so re-adding them puts two of everything in it. Skipping them
    by their PARENT link is not enough: the parent came later, and orders
    placed before it hold studs and nuts with a role and no parent.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.admin = self.env["res.users"].browse(2)
        self.website = self.env["website"].search([], limit=1)
        self.hinge = self.env["product.product"].create({
            "name": "Legacy Probe Hinge", "type": "consu", "list_price": 4.0,
            "is_published": True, "sale_ok": True})
        self.stud = self.env["product.product"].create({
            "name": "1/4 X 3/4 KNURLEL STUD 18-8", "type": "consu",
            "list_price": 0.35, "is_published": True, "sale_ok": True})

    def test_a_loose_fastener_from_an_old_order_is_not_reordered(self):
        order = self.env["sale.order"].create({
            "partner_id": self.admin.partner_id.id,
            "website_id": self.website.id,
            "order_line": [
                (0, 0, {"product_id": self.hinge.id, "product_uom_qty": 2}),
                # As the first version of the rule wrote them: a role, and no
                # parent, because fasteners were then counted per CART.
                (0, 0, {"product_id": self.stud.id, "product_uom_qty": 2,
                        "track_prep_role": "stud"}),
            ],
        })
        order.action_confirm()

        self.authenticate("admin", "admin")
        self.url_open("/my/orders/reorder", data=json.dumps({
            "jsonrpc": "2.0", "method": "call",
            "params": {"order_id": order.id}}),
            headers={"Content-Type": "application/json"})

        cart = self.env["sale.order"].search(
            [("partner_id", "=", self.admin.partner_id.id),
             ("state", "=", "draft")], order="id desc", limit=1)
        loose = cart.order_line.filtered(
            lambda line: line.product_id == self.stud
            and not line.track_prep_parent_id)

        self.assertTrue(cart.order_line, "nothing was reordered at all")
        self.assertFalse(loose, "a part the sync owns was reordered as a product")


@tagged("post_install", "-at_install")
class TestReorderKeepsWhatWasConfigured(HttpCase):
    """A custom spring has to come back as a spring, not as a bare product.

    Odoo reorders by product: it adds each one to the cart as if somebody had
    clicked it in the shop. For a configured assembly that loses both things
    that make it one - the specification, which is written on the line, and the
    price, which was worked out from cone, steel, labour and markup rather
    than looked up.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.admin = self.env["res.users"].browse(2)
        self.website = self.env["website"].search([], limit=1)
        self.spring = self.env.ref(
            "spring_engineering.product_custom_spring").product_variant_id
        self.kit = self.env["product.product"].create({
            "name": "Reorder Kit AA-1200", "type": "consu", "list_price": 290.0,
            "is_published": True, "sale_ok": True})
        self.spec = (
            "Custom Torsion Spring Assembly\n"
            "Duplex, 2 springs\n"
            'Outer: 0.2625" wire, 6" ID, 32.5" long\n'
            'Inner: 0.2253" wire, 3.75" ID, 31.25" long\n'
            "Door: 9' 0\" wide, 7' 0\" high, 355 lb, 10,000 cycles")

    def _order_with_a_spring(self):
        order = self.env["sale.order"].create({
            "partner_id": self.admin.partner_id.id,
            "website_id": self.website.id,
        })
        kit_line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.kit.id,
            "product_uom_qty": 1,
            "aa_spec_note": 'Track: 3" 15R | W 108" x H 84" | 355 lb',
            "aa_door_width_in": 108, "aa_door_height_in": 84,
            "aa_door_weight_lb": 355,
        })
        spring_line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.spring.id,
            "product_uom_qty": 1, "name": self.spec,
            "aa_spec_note": "\n".join(self.spec.splitlines()[1:]),
            "aa_door_weight_lb": 355, "linked_line_id": kit_line.id,
        })
        spring_line.write({"price_unit": 342.56})
        order.action_confirm()

        return order, kit_line, spring_line

    def _cart(self):
        return self.env["sale.order"].search(
            [("partner_id", "=", self.admin.partner_id.id),
             ("state", "=", "draft")], order="id desc", limit=1)

    def _reorder(self, order):
        return self.url_open(
            "/my/orders/reorder",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"order_id": order.id}}),
            headers={"Content-Type": "application/json"}).json()

    def _spring_in_cart(self):
        return self._cart().order_line.filtered(
            lambda line: line.product_id == self.spring)

    def test_the_spring_comes_back_with_its_specification(self):
        order, _kit, _spring = self._order_with_a_spring()
        self.authenticate("admin", "admin")

        self._reorder(order)
        line = self._spring_in_cart()

        self.assertEqual(len(line), 1, "the spring did not come back")
        self.assertIn('0.2625" wire', line.name)
        self.assertIn("355 lb", line.name)
        self.assertIn('0.2625" wire', line.aa_spec_note)

    def test_the_spring_comes_back_at_its_price(self):
        """THE BUG: added as a product it reorders at the catalogue price,
        which this product deliberately sets to nothing."""
        order, _kit, _spring = self._order_with_a_spring()
        self.authenticate("admin", "admin")

        self._reorder(order)

        self.assertEqual(self._spring_in_cart().price_unit, 342.56)

    def test_the_kit_comes_back_with_its_door(self):
        order, _kit, _spring = self._order_with_a_spring()
        self.authenticate("admin", "admin")

        self._reorder(order)
        line = self._cart().order_line.filtered(
            lambda l: l.product_id == self.kit)

        self.assertEqual(line.aa_door_weight_lb, 355)
        self.assertIn('W 108"', line.aa_spec_note or "")

    def test_the_spring_is_still_attached_to_its_kit(self):
        order, _kit, _spring = self._order_with_a_spring()
        self.authenticate("admin", "admin")

        self._reorder(order)
        cart = self._cart()
        kit_line = cart.order_line.filtered(lambda l: l.product_id == self.kit)

        self.assertEqual(self._spring_in_cart().linked_line_id, kit_line)

    def test_a_prepared_tracks_parts_are_not_doubled(self):
        """The cart adds the jamb brackets itself when the track goes in, so
        carrying the old ones over would ship two sets."""
        bracket = self.env["product.product"].create({
            "name": "Jamb Bracket # 10 Black", "type": "consu",
            "list_price": 1.2, "is_published": True, "sale_ok": True})
        track = self.env["product.product"].create({
            "name": 'CH-VT-2-2 Vertical Track 76-7 door height black',
            "type": "consu", "list_price": 42.0, "is_published": True,
            "sale_ok": True})
        order = self.env["sale.order"].create({
            "partner_id": self.admin.partner_id.id,
            "website_id": self.website.id,
        })
        track_line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": track.id, "product_uom_qty": 1})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": bracket.id,
            "product_uom_qty": 4, "track_prep_parent_id": track_line.id,
            "track_prep_role": "jamb_10"})
        order.action_confirm()
        self.authenticate("admin", "admin")

        self._reorder(order)
        brackets = self._cart().order_line.filtered(
            lambda line: line.product_id == bracket)

        self.assertLessEqual(sum(brackets.mapped("product_uom_qty")), 4.0,
                             "the preparation parts were added twice")

    def test_adding_the_spring_as_a_product_is_what_was_wrong(self):
        """WHY THE OVERRIDE EXISTS, shown rather than asserted about.

        This is what Odoo's reorder does to a configured line: it adds the
        product to the cart. The result is the bug the owner met - no
        specification, and the catalogue price, which this product sets to
        nothing on purpose.
        """
        cart = self.env["sale.order"].create({
            "partner_id": self.admin.partner_id.id,
            "website_id": self.website.id,
        })
        cart._cart_add(product_id=self.spring.id, quantity=1)
        line = cart.order_line.filtered(
            lambda l: l.product_id == self.spring)

        self.assertEqual(line.price_unit, 0.0)
        self.assertNotIn('0.2625" wire', line.name or "")


@tagged("post_install", "-at_install")
class TestReorderReplacesTheCart(HttpCase):
    """Reordering says order THIS again, not add this to what is already here.

    And the button that opens the panel has to stay alive while there is still
    something to offer - Odoo greys it out whenever its own product history
    comes back empty, which it does as soon as the cart holds the things the
    customer usually buys.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.admin = self.env["res.users"].browse(2)
        self.website = self.env["website"].search([], limit=1)
        self.hinge = self.env["product.product"].create({
            "name": "Replace Probe Hinge", "type": "consu", "list_price": 4.0,
            "is_published": True, "sale_ok": True})
        self.roller = self.env["product.product"].create({
            "name": "Replace Probe Roller", "type": "consu", "list_price": 9.0,
            "is_published": True, "sale_ok": True})

    def _past_order(self):
        order = self.env["sale.order"].create({
            "partner_id": self.admin.partner_id.id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {"product_id": self.hinge.id,
                                   "product_uom_qty": 3})],
        })
        order.action_confirm()

        return order

    def _cart(self):
        return self.env["sale.order"].search(
            [("partner_id", "=", self.admin.partner_id.id),
             ("state", "=", "draft")], order="id desc", limit=1)

    def _add(self, product, qty=1):
        return self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": product.product_tmpl_id.id,
                "product_id": product.id, "quantity": qty}}),
            headers={"Content-Type": "application/json"})

    def _reorder(self, order):
        return self.url_open(
            "/my/orders/reorder",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"order_id": order.id}}),
            headers={"Content-Type": "application/json"}).json()

    def test_what_was_in_the_cart_is_cleared_out(self):
        order = self._past_order()
        self.authenticate("admin", "admin")
        self._add(self.roller, 5)
        self.assertTrue(self._cart().order_line)

        self._reorder(order)
        cart = self._cart()

        self.assertEqual(
            {(line.product_id, line.product_uom_qty) for line in cart.order_line},
            {(self.hinge, 3.0)},
            "the old cart contents survived the reorder")

    def test_the_panel_says_so_before_anybody_presses_it(self):
        self._past_order()
        self.authenticate("admin", "admin")
        page = self.url_open("/shop/cart").text

        self.assertIn("replacing what is in it", page)

    def test_the_button_is_not_greyed_out_with_a_full_cart(self):
        """Odoo leaves out of its history any product already in the cart, so
        a cart holding what you usually buy disables the button. The orders
        are still there to offer."""
        self._past_order()
        self.authenticate("admin", "admin")
        self._add(self.hinge, 3)

        page = self.url_open("/shop/cart").text
        button = re.search(r"<button[^>]*id=\"quick_reorder_button\"[^>]*>", page)

        self.assertTrue(button, "the quick reorder button is not on the page")
        self.assertNotIn("disabled", button.group(0), button.group(0))
