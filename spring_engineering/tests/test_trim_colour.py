from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTrimColour(TransactionCase):
    """The trim colour on a hardware kit.

    This replaces a JavaScript widget that never worked on the live site. The
    widget swapped Odoo's "Custom value" text box for a dropdown, which needed
    the Trims value flagged by hand on every kit and shipped in a module the
    live site does not install. An attribute needs neither.
    """

    def setUp(self):
        super().setUp()
        self.attr = self.env.ref("spring_engineering.attribute_trim_colour")
        self.values = {
            name: self.env.ref("spring_engineering.attribute_value_trim_%s" % key)
            for key, name in [("none", "No Trim"), ("black", "Black"),
                              ("bronze", "Bronze"), ("white", "White")]
        }

    def _kit(self, name="AA 1200 Hardware Kit"):
        tmpl = self.env["product.template"].create({
            "name": name, "type": "consu", "list_price": 430.11})
        self.env["product.template"]._attach_trim_colour()
        tmpl.invalidate_recordset()

        return tmpl

    def _line(self, tmpl):
        return tmpl.attribute_line_ids.filtered(lambda l: l.attribute_id == self.attr)

    def test_the_three_colours_the_owner_asked_for(self):
        line = self._line(self._kit())
        self.assertTrue(line, "the trim colour was not attached to a hardware kit")
        self.assertEqual(
            sorted(line.value_ids.mapped("name")),
            ["Black", "Bronze", "No Trim", "White"],
        )

    def test_no_trim_is_first_so_it_is_the_default(self):
        # Trims are an extra. A no-variant attribute always has one value
        # selected, so "No Trim" is how a kit says it wants none - and being
        # first is what makes it the answer for a customer who ignores it.
        line = self._line(self._kit())
        first = line.value_ids.sorted(lambda v: v.sequence)[0]
        self.assertEqual(first.name, "No Trim")

    def test_the_choice_reaches_the_order_line(self):
        # The point of using an attribute: nothing collects the value, Odoo
        # records it against the line itself.
        tmpl = self._kit()
        ptav = self._line(tmpl).product_template_value_ids.filtered(
            lambda p: p.name == "Bronze")
        partner = self.env["res.partner"].create({"name": "Trim Buyer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        order._cart_add(
            tmpl.product_variant_id.id, 1,
            no_variant_attribute_value_ids=[ptav.id])
        line = order.order_line[:1]
        self.assertIn(
            "Bronze", line.product_no_variant_attribute_value_ids.mapped("name"))

    def test_it_creates_no_variants(self):
        # Four colours must not turn one kit into four products.
        tmpl = self._kit()
        self.assertEqual(self.attr.create_variant, "no_variant")
        self.assertEqual(len(tmpl.product_variant_ids), 1)

    def test_it_is_hidden_from_the_shop_filters(self):
        # The prepared-track option appeared down the side of /shop under the
        # categories before this was set. A catalogue is not browsed by trim.
        self.assertEqual(self.attr.visibility, "hidden")

    def test_it_is_not_put_on_other_products(self):
        other = self.env["product.template"].create({
            "name": "2\" Vertical Track 76\" - 7' Door Height Black",
            "type": "consu"})
        self.env["product.template"]._attach_trim_colour()
        other.invalidate_recordset()
        self.assertFalse(self._line(other))

    def test_attaching_twice_changes_nothing(self):
        tmpl = self._kit()
        before = len(tmpl.attribute_line_ids)
        self.env["product.template"]._attach_trim_colour()
        self.env["product.template"]._attach_trim_colour()
        tmpl.invalidate_recordset()
        self.assertEqual(len(tmpl.attribute_line_ids), before)
