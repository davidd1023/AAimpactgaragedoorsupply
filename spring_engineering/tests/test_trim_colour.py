from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTrimColour(TransactionCase):
    """The trim colour on a hardware kit.

    This replaces a JavaScript widget that never worked on the live site. The
    widget swapped Odoo's "Custom value" text box for a dropdown, which needed
    the Trims value flagged by hand on every kit and shipped in a module the
    live site does not install. An attribute needs neither.

    WHAT WAS RULED OUT when the owner reported that the chosen colour always
    came back as "No Trim". Written down because it cost an afternoon and the
    next person should not repeat it:

      - the BACKEND IS NOT AT FAULT. A kit built to the same shape as the live
        one - a variant attribute, a single-value attribute, AND the multi
        checkbox "Add to Your Order" - records and prints the choice:
            STORED: ['Springs', 'Bronze, 3 Trim']
            LINE  : ... (4 Panels) | Trims: Bronze, 3 Trim | ...: Springs
      - visibility="hidden" does NOT break it. It only removes the attribute
        from the /shop sidebar filters; the model test passes with it set.
      - the radios carry the classes website_sale collects
        (input.no_variant.js_variant_change:checked) and sit inside the
        add-to-cart form, checked against the served HTML.
      - a second add cannot merge into the first line and lose the colour:
        _cart_find_product_line matches on no-variant values whenever the
        product has a no-variant attribute with more than one value.
      - there are NOT two competing trim controls on the page. A screenshot of
        the live kit shows one, and it already carries the renamed values.

    The order line the owner quoted read "Trim Color: No Trim" - the names from
    BEFORE the rename - so it was created by an earlier build. What remains
    untested is the browser-to-server step, which needs a browser this
    container does not have.
    """

    def setUp(self):
        super().setUp()
        self.attr = self.env.ref("spring_engineering.attribute_trim_colour")
        self.values = {
            name: self.env.ref("spring_engineering.attribute_value_trim_%s" % key)
            for key, name in [("none", "No Trims"), ("black", "Black, 3 Trim"),
                              ("bronze", "Bronze, 3 Trim"), ("white", "White, 3 Trim")]
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
        self.assertTrue(line, "the trims option was not attached to a hardware kit")
        self.assertEqual(
            sorted(line.value_ids.mapped("name")),
            ["Black, 3 Trim", "Bronze, 3 Trim", "No Trims", "White, 3 Trim"],
        )

    def test_no_trims_is_first_so_it_is_the_default(self):
        # Trims are an extra. A no-variant attribute always has one value
        # selected, so "No Trim" is how a kit says it wants none - and being
        # first is what makes it the answer for a customer who ignores it.
        line = self._line(self._kit())
        first = line.value_ids.sorted(lambda v: v.sequence)[0]
        self.assertEqual(first.name, "No Trims")

    def test_the_choice_reaches_the_order_line(self):
        # The point of using an attribute: nothing collects the value, Odoo
        # records it against the line itself.
        tmpl = self._kit()
        ptav = self._line(tmpl).product_template_value_ids.filtered(
            lambda p: p.name == "Bronze, 3 Trim")
        partner = self.env["res.partner"].create({"name": "Trim Buyer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        order._cart_add(
            tmpl.product_variant_id.id, 1,
            no_variant_attribute_value_ids=[ptav.id])
        line = order.order_line[:1]
        self.assertIn(
            "Bronze, 3 Trim",
            line.product_no_variant_attribute_value_ids.mapped("name"))

        # THE LINE HAS TO READ THE WAY THE OWNER ASKED: "Trims: Black, 3 Trim".
        # Odoo prints an attribute as "<attribute>: <value>", so the count
        # living in the value name is what produces that exactly.
        self.assertIn("Trims: Bronze, 3 Trim", line.name or "")

    def test_a_kit_with_no_trims_says_so(self):
        tmpl = self._kit()
        ptav = self._line(tmpl).product_template_value_ids.filtered(
            lambda p: p.name == "No Trims")
        partner = self.env["res.partner"].create({"name": "No Trim Buyer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        order._cart_add(
            tmpl.product_variant_id.id, 1,
            no_variant_attribute_value_ids=[ptav.id])
        self.assertIn("Trims: No Trims", order.order_line[:1].name or "")

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
