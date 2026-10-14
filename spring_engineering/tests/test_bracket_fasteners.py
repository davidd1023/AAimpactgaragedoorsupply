from odoo.tests.common import TransactionCase, tagged


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
        """A 7 ft door takes four each of three sizes - so twelve of each
        fastener, not one set per track."""
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
        self.assertEqual(self._qty(order, self.stud), 12)
        self.assertEqual(self._qty(order, self.nut), 12)

    def test_two_prepared_tracks_take_twice_as_many(self):
        order = self._order()
        tmpl = self._track()
        order._cart_add(
            product_id=tmpl.product_variant_id.id, quantity=2,
            no_variant_attribute_value_ids=[
                self._ptav(tmpl, "Prepared").id])

        self.assertEqual(self._qty(order, self.stud), 24)
        self.assertEqual(self._qty(order, self.nut), 24)

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
