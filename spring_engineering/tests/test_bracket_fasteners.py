import json
import re

from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBracketFasteners(TransactionCase):
    """A jamb bracket never ships without its stud and its flange nut.

    One of each PER BRACKET, wherever the bracket came from: bought on its own
    in the shop, or brought in by a prepared track, which adds a graduated mix
    of sizes by itself.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Fastener Buyer"})
        self.stud = self.env["product.product"].create({
            "name": "1/4 X 3/4 KNURLEL STUD 18-8", "type": "consu",
            "list_price": 0.35, "sale_ok": True, "is_published": True})
        self.nut = self.env["product.product"].create({
            "name": "Flage Nuts 1/4 20", "type": "consu",
            "list_price": 0.2, "sale_ok": True, "is_published": True})
        self.lag = self.env["product.product"].create({
            "name": "Lag Screws", "type": "consu",
            "list_price": 0.4, "sale_ok": True, "is_published": True})
        self.bracket = self.env["product.product"].search(
            [("default_code", "=", "ATL-610J10JBBR")], limit=1)
        self.assertTrue(self.bracket, "the catalogue bracket is missing")

        self.attr = self.env.ref("spring_engineering.attribute_track_preparation")
        self.prepared = self.env.ref(
            "spring_engineering.attribute_value_track_prepared")
        self.unprepared = self.env.ref(
            "spring_engineering.attribute_value_track_unprepared")

    def _order(self):
        return self.env["sale.order"].create({"partner_id": self.partner.id})

    def _qty(self, order, product):
        return sum(order.order_line.filtered(
            lambda line: line.product_id == product).mapped("product_uom_qty"))

    def _track(self):
        tmpl = self.env["product.template"].create({
            "name": "CH-VT-2-2 Vertical Track 76-7 door height black",
            "type": "consu", "list_price": 42.0})
        self.env["product.template.attribute.line"].create({
            "product_tmpl_id": tmpl.id, "attribute_id": self.attr.id,
            "value_ids": [(6, 0, [self.unprepared.id, self.prepared.id])]})
        tmpl.invalidate_recordset()

        return tmpl

    def _ptav(self, tmpl, name):
        return tmpl.attribute_line_ids.filtered(
            lambda l: l.attribute_id == self.attr
        ).product_template_value_ids.filtered(lambda p: p.name == name)

    # --- a bracket bought on its own -----------------------------------------

    def test_buying_brackets_brings_one_of_each_per_bracket(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=4)

        self.assertEqual(self._qty(order, self.stud), 4)
        self.assertEqual(self._qty(order, self.nut), 4)

    def test_the_count_follows_the_brackets(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=4)
        line = order.order_line.filtered(
            lambda l: l.product_id == self.bracket)[:1]

        order._cart_update_line_quantity(line.id, 7)

        self.assertEqual(self._qty(order, self.stud), 7)
        self.assertEqual(self._qty(order, self.nut), 7)

    def test_taking_the_brackets_out_takes_them_with_it(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=2)
        line = order.order_line.filtered(
            lambda l: l.product_id == self.bracket)[:1]

        order._cart_update_line_quantity(line.id, 0)

        self.assertEqual(self._qty(order, self.stud), 0)
        self.assertEqual(self._qty(order, self.nut), 0)

    def test_a_cart_without_brackets_has_none_of_them(self):
        order = self._order()
        order._cart_add(product_id=self.nut.id, quantity=3)

        # The nut bought deliberately is left exactly as it was: it carries no
        # role, so the rule does not own it.
        self.assertEqual(self._qty(order, self.nut), 3)
        self.assertEqual(self._qty(order, self.stud), 0)

    # --- and a prepared track, which brings its own ---------------------------

    def test_a_prepared_track_counts_every_bracket_it_adds(self):
        """A 7 ft door takes four each of three sizes - twelve brackets, so
        twelve studs - PLUS the flag angle's own four, which it has taken
        since the owner's second list of companions. Sixteen is the whole
        track's worth, not one set per track."""
        order = self._order()
        tmpl = self._track()
        order._cart_add(
            product_id=tmpl.product_variant_id.id, quantity=1,
            no_variant_attribute_value_ids=[
                self._ptav(tmpl, "Prepared").id])

        brackets = sum(
            line.product_uom_qty for line in order.order_line
            if order._fastener_is_bracket(line))

        self.assertEqual(brackets, 12, "the fixture is not the mix expected")
        self.assertEqual(self._qty(order, self.stud), 16, "12 brackets + 4 flag")
        self.assertEqual(self._qty(order, self.nut), 16)
        # One per bracket, three for the flag angle.
        self.assertEqual(self._qty(order, self.lag), 15)

    def test_two_prepared_tracks_take_twice_as_many(self):
        order = self._order()
        tmpl = self._track()
        order._cart_add(
            product_id=tmpl.product_variant_id.id, quantity=2,
            no_variant_attribute_value_ids=[
                self._ptav(tmpl, "Prepared").id])

        self.assertEqual(self._qty(order, self.stud), 32)
        self.assertEqual(self._qty(order, self.nut), 32)
        self.assertEqual(self._qty(order, self.lag), 30)

    def test_an_unprepared_track_brings_nothing(self):
        order = self._order()
        tmpl = self._track()
        order._cart_add(
            product_id=tmpl.product_variant_id.id, quantity=1,
            no_variant_attribute_value_ids=[
                self._ptav(tmpl, "Unprepared").id])

        self.assertEqual(self._qty(order, self.stud), 0)

    # --- the parts themselves -------------------------------------------------

    def test_a_customer_cannot_edit_the_fasteners_on_their_own(self):
        """The cart owes one per bracket; changing that by hand would ship
        brackets nobody can fit."""
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=4)
        stud_line = order.order_line.filtered(
            lambda l: l.product_id == self.stud)[:1]

        order._cart_update_line_quantity(stud_line.id, 1)

        self.assertEqual(self._qty(order, self.stud), 4)

    def test_the_name_is_read_tolerantly(self):
        """A name typed twice is a name typed differently - the owner's own
        spelling says KNURLEL and Flage."""
        self.stud.name = "1/4 x 3/4 Knurled Stud 18-8 Stainless"
        self.nut.name = "FLANGE NUTS 1/4-20 Zinc"
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=2)

        self.assertEqual(self._qty(order, self.stud), 2)
        self.assertEqual(self._qty(order, self.nut), 2)

    def test_a_missing_part_is_named_rather_than_skipped(self):
        order = self._order()
        self.stud.unlink()

        warning = None
        result = order._cart_add(product_id=self.bracket.id, quantity=2)
        warning = result.get("warning")

        self.assertTrue(warning, "nothing was said about the missing stud")
        self.assertIn("KNURLEL", warning)
        # The nut it CAN find still goes in - half a set beats none.
        self.assertEqual(self._qty(order, self.nut), 2)

    # --- the ways a bracket can leave ----------------------------------------

    def test_removing_a_tracks_own_bracket_takes_the_fasteners_too(self):
        """THE BUG: taking a prepared track away by removing one of its parts
        goes down a branch that returned early, so the studs and nuts stayed
        behind with the quantity the brackets used to have - a cart holding
        nothing but fasteners, and a counter still counting them."""
        order = self._order()
        tmpl = self._track()
        order._cart_add(
            product_id=tmpl.product_variant_id.id, quantity=1,
            no_variant_attribute_value_ids=[self._ptav(tmpl, "Prepared").id])
        self.assertEqual(self._qty(order, self.stud), 16)

        bracket_line = order.order_line.filtered(
            lambda line: order._fastener_is_bracket(line))[:1]
        order._cart_update_line_quantity(bracket_line.id, 0)

        self.assertEqual(self._qty(order, self.stud), 0)
        self.assertEqual(self._qty(order, self.nut), 0)
        self.assertFalse(order.order_line, "the cart kept something")
        self.assertEqual(order.cart_quantity, 0,
                         "the counter still counts what is not there")

    def test_removing_the_track_itself_takes_them_too(self):
        order = self._order()
        tmpl = self._track()
        order._cart_add(
            product_id=tmpl.product_variant_id.id, quantity=1,
            no_variant_attribute_value_ids=[self._ptav(tmpl, "Prepared").id])
        track_line = order.order_line.filtered(
            lambda line: line.product_id == tmpl.product_variant_id)[:1]

        order._cart_update_line_quantity(track_line.id, 0)

        self.assertEqual(order.cart_quantity, 0)
        self.assertFalse(order.order_line)

    def test_a_stud_whose_bracket_went_first_does_not_fail(self):
        """THE OTHER HALF: the "Missing Record" the owner saw.

        Pressing Remove on a stud whose bracket has already gone used to read
        the answer off a record the rule had just deleted. Now the bracket
        takes its own fasteners with it as it goes - the link cascades - so by
        the time a click for that row arrives the row is not there at all, and
        the worst that may happen is website_sale's own "refresh your page",
        which is exactly what a stale tab deserves. What must NOT happen is
        an exception.
        """
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=2)
        bracket_line = order.order_line.filtered(
            lambda line: line.product_id == self.bracket)[:1]
        stud_line = order.order_line.filtered(
            lambda line: line.product_id == self.stud)[:1]
        self.assertTrue(stud_line, "the stud came with the brackets")

        bracket_line.unlink()

        self.assertFalse(stud_line.exists(), "the bracket took its stud along")

        answer = order._cart_update_line_quantity(stud_line.id, 0)

        self.assertNotIn("quantity", answer, "there is no such line to report")
        self.assertIn("warning", answer)
        self.assertFalse(order.order_line, "nothing was left behind")

    def test_a_fastener_pressed_while_brackets_remain_comes_back(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=3)
        stud_line = order.order_line.filtered(
            lambda line: line.product_id == self.stud)[:1]

        answer = order._cart_update_line_quantity(stud_line.id, 0)

        self.assertEqual(answer["quantity"], 3)
        self.assertEqual(self._qty(order, self.stud), 3)


@tagged("post_install", "-at_install")
class TestTheHeaderCount(HttpCase):
    """The number on the cart icon has to mean the cart.

    website_sale caches cart_quantity in the SESSION - a page rendered
    afterwards reads that rather than counting the lines - so moving lines
    underneath it leaves the number stale. The owner saw 24 over an empty cart,
    and it only corrected itself when something else was added.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.stud = self.env["product.product"].create({
            "name": "1/4 X 3/4 KNURLEL STUD 18-8", "type": "consu",
            "list_price": 0.35, "sale_ok": True, "is_published": True})
        self.nut = self.env["product.product"].create({
            "name": "Flage Nuts 1/4 20", "type": "consu",
            "list_price": 0.2, "sale_ok": True, "is_published": True})
        self.lag = self.env["product.product"].create({
            "name": "Lag Screws", "type": "consu",
            "list_price": 0.4, "sale_ok": True, "is_published": True})
        self.bracket = self.env["product.product"].search(
            [("default_code", "=", "ATL-610J10JBBR")], limit=1)
        self.bracket.product_tmpl_id.write({"is_published": True})

    def _json(self, route, params):
        return self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"}).json()

    def _cart(self):
        return self.env["sale.order"].search(
            [("partner_id", "=", self.env["res.users"].browse(2).partner_id.id),
             ("state", "=", "draft")], order="id desc", limit=1)

    def test_the_header_number_follows_the_fasteners_out(self):
        self.authenticate("admin", "admin")
        self._json("/shop/cart/add", {
            "product_template_id": self.bracket.product_tmpl_id.id,
            "product_id": self.bracket.id, "quantity": 4})
        cart = self._cart()

        # THE BADGE COUNTS WHAT THE CART SHOWS. The studs and nuts are on the
        # order - four of each - but they ride under the bracket now rather
        # than standing as rows of their own, so they are not counted twice
        # over. A badge of 12 above four visible rows is the disagreement the
        # owner reported from the other side.
        self.assertEqual(cart.cart_quantity, 4, "four bracket rows")
        self.assertEqual(
            sum(cart.order_line.filtered(
                lambda line: line.product_id == self.stud
            ).mapped("product_uom_qty")), 4, "the studs are still on the order")

        bracket_line = cart.order_line.filtered(
            lambda line: line.product_id == self.bracket)[:1]
        answer = self._json("/shop/cart/update",
                            {"line_id": bracket_line.id, "quantity": 0})

        cart.invalidate_recordset()
        self.assertEqual(cart.cart_quantity, 0, "the cart still holds something")
        self.assertEqual(answer["result"]["cart_quantity"], 0,
                         "the page was told the old number")

    def test_the_cart_page_agrees_with_itself(self):
        """The page renders its own header from the cached figure, so the two
        halves of the same screen have to say the same thing."""
        self.authenticate("admin", "admin")
        self._json("/shop/cart/add", {
            "product_template_id": self.bracket.product_tmpl_id.id,
            "product_id": self.bracket.id, "quantity": 2})
        cart = self._cart()
        bracket_line = cart.order_line.filtered(
            lambda line: line.product_id == self.bracket)[:1]
        self._json("/shop/cart/update",
                   {"line_id": bracket_line.id, "quantity": 0})

        page = self.url_open("/shop/cart").text
        badge = re.search(r"<sup[^>]*my_cart_quantity[^>]*>\s*([0-9]+)", page)

        self.assertIn("Your cart is empty", page)
        self.assertTrue(badge, "the header carries no count at all")
        self.assertEqual(badge.group(1), "0",
                         "the header counts what the page says is not there")


@tagged("post_install", "-at_install")
class TestFastenersStackUnderTheBracket(HttpCase):
    """One row in the cart, three things in the box.

    The fasteners hang off the bracket line itself: the cart folds them under
    it, the price on that row is the price of all three, and removing the
    bracket takes them with it.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.partner = self.env["res.users"].browse(2).partner_id
        self.stud = self.env["product.product"].create({
            "name": "1/4 X 3/4 KNURLEL STUD 18-8", "type": "consu",
            "list_price": 0.5, "sale_ok": True, "is_published": True})
        self.nut = self.env["product.product"].create({
            "name": "Flage Nuts 1/4 20", "type": "consu",
            "list_price": 0.25, "sale_ok": True, "is_published": True})
        self.lag = self.env["product.product"].create({
            "name": "Lag Screws", "type": "consu",
            "list_price": 0.4, "sale_ok": True, "is_published": True})
        self.bracket = self.env["product.product"].search(
            [("default_code", "=", "ATL-610J10JBBR")], limit=1)
        self.bracket.product_tmpl_id.write({"is_published": True})

    def _order(self):
        return self.env["sale.order"].create({"partner_id": self.partner.id})

    def _bracket_line(self, order):
        return order.order_line.filtered(
            lambda line: line.product_id == self.bracket)[:1]

    def test_the_pair_hangs_off_the_bracket_that_needs_it(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=4)
        bracket = self._bracket_line(order)

        self.assertEqual(len(bracket.aa_included_line_ids), 3,
                         "a stud, a nut and a lag screw")
        self.assertEqual(
            set(bracket.aa_included_line_ids.mapped("product_id")),
            {self.stud, self.nut, self.lag})
        self.assertEqual(
            set(bracket.aa_included_line_ids.mapped("product_uom_qty")), {4.0})

    def test_each_bracket_size_gets_its_own_pair(self):
        """A prepared track brings three bracket lines; a pair counted across
        the cart could not say which went with which."""
        attr = self.env.ref("spring_engineering.attribute_track_preparation")
        prepared = self.env.ref(
            "spring_engineering.attribute_value_track_prepared")
        tmpl = self.env["product.template"].create({
            "name": "CH-VT-2-2 Vertical Track 76-7 door height black",
            "type": "consu", "list_price": 42.0,
            "attribute_line_ids": [(0, 0, {
                "attribute_id": attr.id, "value_ids": [(6, 0, [prepared.id])]})],
        })
        tmpl.invalidate_recordset()
        ptav = tmpl.attribute_line_ids.product_template_value_ids[:1]
        order = self._order()
        order._cart_add(product_id=tmpl.product_variant_id.id, quantity=1,
                        no_variant_attribute_value_ids=[ptav.id])

        brackets = order.order_line.filtered(order._fastener_is_bracket)
        self.assertEqual(len(brackets), 3, "the fixture is not the mix expected")

        for bracket in brackets:
            self.assertEqual(len(bracket.aa_included_line_ids), 3,
                             bracket.product_id.display_name)
            self.assertEqual(
                set(bracket.aa_included_line_ids.mapped("product_uom_qty")),
                {bracket.product_uom_qty})

    def test_removing_the_bracket_takes_them_with_it(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=2)
        bracket = self._bracket_line(order)
        parts = bracket.aa_included_line_ids

        bracket.unlink()

        self.assertFalse(parts.exists(), "the fasteners outlived the bracket")

    def test_they_are_not_rows_of_their_own(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=2)
        bracket = self._bracket_line(order)

        self.assertIn(bracket, order.website_order_line)
        for part in bracket.aa_included_line_ids:
            self.assertNotIn(part, order.website_order_line)
            self.assertFalse(part._show_in_cart())

    def test_the_price_on_the_row_is_the_price_of_all_three(self):
        order = self._order()
        order._cart_add(product_id=self.bracket.id, quantity=2)
        bracket = self._bracket_line(order)
        parts = bracket.aa_included_line_ids

        shown = bracket._get_cart_display_price()
        alone = bracket.price_subtotal if (
            order.website_id.show_line_subtotals_tax_selection == "tax_excluded"
        ) else bracket.price_total

        self.assertGreater(shown, alone, "the fasteners are free of charge")

        # One record at a time: the hook reads fields off self, so core's own
        # version raises on a recordset too. A fastener stands for itself.
        for part in parts:
            self.assertEqual(part._get_lines_with_price(), part)

    def test_the_cart_page_folds_them_under_it(self):
        self.authenticate("admin", "admin")
        self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": self.bracket.product_tmpl_id.id,
                "product_id": self.bracket.id, "quantity": 2}}),
            headers={"Content-Type": "application/json"})

        page = self.url_open("/shop/cart").text

        self.assertIn("Comes with", page)
        self.assertIn("data-bs-toggle=\"collapse\"", page)
        self.assertIn("KNURLEL", page)
        # Folded away, not hidden from the customer: the list is in the page,
        # inside a collapse the caret opens.
        self.assertIn("collapse list-unstyled", page)


@tagged("post_install", "-at_install")
class TestBuyingABracketBesideAPreparedTrack(TransactionCase):
    """The owner's cart, 2026-10-15: a prepared track in it, then a jamb
    bracket added from the shop - and the page died on a server error.

    Odoo adds by looking for a line that already holds that product, and the
    prepared track had made one. The add was handed the TRACK's bracket line,
    which this module refuses to let anybody edit on its own, and the refusal
    answered in the shape the cart page reads rather than the one the add
    route reads: KeyError: 'added_qty'.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Bracket Buyer"})
        self.stud = self.env["product.product"].create({
            "name": "1/4 X 3/4 KNURLEL STUD 18-8", "type": "consu",
            "list_price": 0.35, "sale_ok": True, "is_published": True})
        self.nut = self.env["product.product"].create({
            "name": "Flage Nuts 1/4 20", "type": "consu",
            "list_price": 0.2, "sale_ok": True, "is_published": True})
        self.lag = self.env["product.product"].create({
            "name": "Lag Screws", "type": "consu",
            "list_price": 0.4, "sale_ok": True, "is_published": True})
        self.attr = self.env.ref("spring_engineering.attribute_track_preparation")
        self.prepared = self.env.ref(
            "spring_engineering.attribute_value_track_prepared")
        self.unprepared = self.env.ref(
            "spring_engineering.attribute_value_track_unprepared")

    def _cart_with_a_prepared_track(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        tmpl = self.env["product.template"].create({
            "name": "CH-VT-2-2 Vertical Track 76-7 door height black",
            "type": "consu", "list_price": 42.0})
        self.env["product.template.attribute.line"].create({
            "product_tmpl_id": tmpl.id, "attribute_id": self.attr.id,
            "value_ids": [(6, 0, [self.unprepared.id, self.prepared.id])]})
        tmpl.invalidate_recordset()
        ptav = tmpl.attribute_line_ids.filtered(
            lambda l: l.attribute_id == self.attr
        ).product_template_value_ids.filtered(lambda p: p.name == "Prepared")
        order._cart_add(product_id=tmpl.product_variant_id.id, quantity=1,
                        no_variant_attribute_value_ids=[ptav.id])

        return order

    def _a_bracket_the_track_brought(self, order):
        return order.order_line.filtered(
            lambda line: order._fastener_is_bracket(line)
            and line.track_prep_role)[:1]

    def test_adding_a_bracket_the_track_already_brought_answers_properly(self):
        """THE CRASH ITSELF. Whatever else is decided, the answer has to carry
        the keys Odoo's add route reads off it."""
        order = self._cart_with_a_prepared_track()
        bracket = self._a_bracket_the_track_brought(order)
        self.assertTrue(bracket, "the fixture brought no brackets")

        answer = order._cart_add(product_id=bracket.product_id.id, quantity=2)

        for key in ("added_qty", "line_id", "quantity", "warning"):
            self.assertIn(key, answer, f"the add route reads {key}")

    def test_the_customer_gets_a_line_of_their_own(self):
        """AND THE POINT OF IT. The brackets the track owns are the track's;
        brackets the customer asks for are theirs, on their own line, which
        the sync has no business touching."""
        order = self._cart_with_a_prepared_track()
        bracket = self._a_bracket_the_track_brought(order)
        owned_before = bracket.product_uom_qty

        order._cart_add(product_id=bracket.product_id.id, quantity=2)

        mine = order.order_line.filtered(
            lambda line: line.product_id == bracket.product_id
            and not line.track_prep_role)

        self.assertEqual(len(mine), 1, "no line of the customer's own")
        self.assertEqual(mine.product_uom_qty, 2)
        self.assertEqual(bracket.product_uom_qty, owned_before,
                         "the track's own brackets were changed")

    def test_the_loose_brackets_bring_their_own_fasteners(self):
        order = self._cart_with_a_prepared_track()
        bracket = self._a_bracket_the_track_brought(order)
        studs_before = sum(order.order_line.filtered(
            lambda line: line.product_id == self.stud).mapped("product_uom_qty"))

        order._cart_add(product_id=bracket.product_id.id, quantity=2)

        studs_after = sum(order.order_line.filtered(
            lambda line: line.product_id == self.stud).mapped("product_uom_qty"))

        self.assertEqual(studs_after, studs_before + 2,
                         "a bracket still never ships without its stud")

    def test_the_track_can_still_be_found_by_its_own_add(self):
        """THE FILTER MUST NOT HIDE ORDINARY LINES. Adding the same track
        twice still has to find the first one rather than make a second."""
        order = self._cart_with_a_prepared_track()
        track = order.order_line.filtered(
            lambda line: not line.track_prep_role)[:1]

        order._cart_add(product_id=track.product_id.id, quantity=1,
                        no_variant_attribute_value_ids=track
                        .product_no_variant_attribute_value_ids.ids)

        tracks = order.order_line.filtered(
            lambda line: line.product_id == track.product_id
            and not line.track_prep_role)

        self.assertEqual(len(tracks), 1, "the track was added twice")


@tagged("post_install", "-at_install")
class TestWhatElseTakesCompanions(TransactionCase):
    """The owner's second list, 2026-10-16.

    A jamb bracket also takes a lag screw; a flag angle takes three lag
    screws, four studs and four nuts; end bearing plates take two lag screws
    and four track/hanger bolts; spring anchor brackets take two lag screws.
    One table, because they are one rule: something that cannot be fitted
    with what is in the box.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Fitter"})
        self.stud = self._product("1/4 X 3/4 KNURLEL STUD 18-8")
        self.nut = self._product("Flage Nuts 1/4 20")
        self.lag = self._product("Lag Screws")
        self.bolt = self._product("Track/Hanger Bolt/Nut")

    def _product(self, name):
        return self.env["product.product"].create({
            "name": name, "type": "consu", "list_price": 1.0,
            "sale_ok": True, "is_published": True})

    def _cart_with(self, product, quantity=1):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        order._cart_add(product_id=product.id, quantity=quantity)

        return order

    def _qty(self, order, product):
        return sum(order.order_line.filtered(
            lambda line: line.product_id == product).mapped("product_uom_qty"))

    # --- each of the four ----------------------------------------------------

    def test_a_jamb_bracket_now_takes_a_lag_screw_as_well(self):
        bracket = self.env["product.product"].search(
            [("default_code", "=", "ATL-610J10JBBR")], limit=1)
        order = self._cart_with(bracket, 4)

        self.assertEqual(self._qty(order, self.lag), 4, "one per bracket")
        self.assertEqual(self._qty(order, self.stud), 4, "and still a stud")
        self.assertEqual(self._qty(order, self.nut), 4, "and still a nut")

    def test_a_flag_angle_takes_three_lag_four_stud_four_nut(self):
        order = self._cart_with(self._product("Flag Angle Black"))

        self.assertEqual(self._qty(order, self.lag), 3)
        self.assertEqual(self._qty(order, self.stud), 4)
        self.assertEqual(self._qty(order, self.nut), 4)

    def test_an_end_bearing_plate_takes_two_lag_and_four_track_bolts(self):
        order = self._cart_with(self._product("End Bearing Plate 8GA LH"))

        self.assertEqual(self._qty(order, self.lag), 2)
        self.assertEqual(self._qty(order, self.bolt), 4)
        self.assertFalse(self._qty(order, self.stud), "it takes no studs")

    def test_the_track_bolt_is_not_the_hex_lag_bolt(self):
        """BOTH ARE BOLTS, and only one of them is this one. A read for the
        word "bolt" alone would hand the bearing plates a 5/16 hex lag bolt,
        which is why the pattern asks for HANGER as well."""
        hex_bolt = self._product("5/16 x 1-5/8 Hex Lag Bolt")
        order = self._cart_with(self._product("End Bearing Plate 8GA LH"))

        self.assertEqual(self._qty(order, self.bolt), 4)
        self.assertFalse(self._qty(order, hex_bolt), "the wrong bolt")
        self.assertEqual(self._qty(order, self.lag), 2, "nor is it the lag")

    def test_a_spring_anchor_bracket_takes_two_lag_screws(self):
        order = self._cart_with(self._product("Spring Anchor Bracket"))

        self.assertEqual(self._qty(order, self.lag), 2)
        self.assertFalse(self._qty(order, self.bolt), "and no track bolts")

    # --- and the edges of the table -----------------------------------------

    def test_a_pair_counts_as_one_line(self):
        """The owner's instruction: two lag screws for the line, not two for
        each plate the word Pair might mean."""
        order = self._cart_with(
            self._product("End Bearing Plate 3 3-8 Black ( Pair )"))

        self.assertEqual(self._qty(order, self.lag), 2)
        self.assertEqual(self._qty(order, self.bolt), 4)

    def test_the_count_follows_the_quantity(self):
        order = self._cart_with(self._product("End Bearing Plate 8GA RH"), 3)

        self.assertEqual(self._qty(order, self.lag), 6, "two for each ordered")
        self.assertEqual(self._qty(order, self.bolt), 12, "and four each")

    def test_things_that_take_nothing_still_take_nothing(self):
        """A LOOSE SEARCH FOR THREE LETTERS FINDS EVERY FLAG ANGLE. The lag
        screw is matched on a word boundary for exactly that reason, and
        these are the names that would otherwise be caught by a careless
        rule."""
        for name in ("Center Bearing Bracket LH", "EBF-338 End Bearing Flange",
                     "Torsion Solid Shaft 9'6\"", "3\" Lock Black"):
            order = self._cart_with(self._product(name))

            self.assertFalse(self._qty(order, self.lag), name)
            self.assertFalse(self._qty(order, self.stud), name)
            self.assertFalse(self._qty(order, self.bolt), name)

    def test_a_lag_screw_does_not_breed_lag_screws(self):
        """A companion is never a host. Nothing in the table matches one
        today, and a rule that let it would not stop."""
        bracket = self.env["product.product"].search(
            [("default_code", "=", "ATL-610J10JBBR")], limit=1)
        order = self._cart_with(bracket, 1)

        self.assertEqual(self._qty(order, self.lag), 1)

        order._fastener_sync()
        order._fastener_sync()

        self.assertEqual(self._qty(order, self.lag), 1, "it grew on its own")
