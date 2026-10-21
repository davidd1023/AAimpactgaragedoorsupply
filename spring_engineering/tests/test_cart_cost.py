import json
import math
import re

from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.spring_engineering.pricing import (
    CONE_PRICES, FILLER_PRICE_PER_FOOT, STEEL_COST_PER_LB,
)


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
class TestCustomSpringCost(TransactionCase):
    """A custom spring is costed the way it was priced.

    The quote charges cones plus steel: the cones at what they cost us, the
    steel at a price per pound that SELLS - labour and margin inside it. So
    the cost of the same assembly is the same sum with the cost per pound in
    its place, off the same stored specification and the same closed form for
    the weight. Nothing is worked backwards from the price, because nothing in
    a selling rate can be.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.partner = self.env["res.partner"].create({"name": "Spring Coster"})
        self.spring = self.env.ref(
            "spring_engineering.product_custom_spring").product_variant_id
        self.filler = self.env.ref(
            "spring_engineering.product_custom_filler").product_variant_id
        self.rate(STEEL_COST_PER_LB)

    def rate(self, value):
        self.env["ir.config_parameter"].sudo().set_param(
            "spring_engineering.steel_cost_per_lb", str(value))

    def _density(self):
        from odoo.addons.spring_engineering.controllers.main import (
            _calculator_constants,
        )

        return _calculator_constants()["density"]

    def _weight(self, wire, diameter, length):
        """The published closed form, spelled out here rather than imported.

        density * (pi^2 / 4) * wire * (ID + wire) * length, to the cent. If
        the two ever disagree this test is the one that should fail.
        """
        volume = (math.pi ** 2) / 4 * wire * (diameter + wire) * length

        return round(self._density() * volume, 2)

    def _assembly(self, items, springs=2, qty=1, spec=True):
        """A spring line as add_assembly_lines books one."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})
        order.order_line = [(0, 0, {
            "product_id": self.spring.id, "product_uom_qty": qty,
            "price_unit": 410.0, "discount": 0.0})]

        if spec:
            order.order_line[0].spring_spec_json = json.dumps({
                "assembly": "Single", "springs": springs,
                "lh": (springs + 1) // 2, "rh": springs - (springs + 1) // 2,
                "items": [
                    {"role": "Spring", "wire": wire, "id": diameter,
                     "length": length}
                    for wire, diameter, length in items
                ],
                "door": {"weight": 355, "height": "7' 0\"", "cycles": 10000},
            })

        return order

    # --- the sum --------------------------------------------------------------

    def test_a_single_spring_costs_its_cones_plus_its_steel(self):
        order = self._assembly([(0.2625, 3.75, 30.0)], springs=2)
        cones = round(2 * CONE_PRICES[3.75], 2)
        steel = round(2 * self._weight(0.2625, 3.75, 30.0) * STEEL_COST_PER_LB, 2)

        self.assertEqual(order._aa_cart_cost(),
                         {"cost": round(cones + steel, 2), "unpriced": 0})

    def test_the_cost_rate_is_used_and_not_the_selling_rate(self):
        """THE WHOLE POINT. The per-pound setting the quotes use is a sale
        price with the labour and the margin in it; costing a spring with it
        would print the sale price back as a cost."""
        sell = 1.46
        self.env["ir.config_parameter"].sudo().set_param(
            "spring_engineering.steel_per_lb", str(sell))
        self.rate(0.81)
        order = self._assembly([(0.2625, 3.75, 30.0)], springs=2)
        weight = 2 * self._weight(0.2625, 3.75, 30.0)
        cones = round(2 * CONE_PRICES[3.75], 2)

        self.assertEqual(order._aa_cart_cost()["cost"],
                         round(cones + round(weight * 0.81, 2), 2))
        self.assertNotEqual(order._aa_cart_cost()["cost"],
                            round(cones + round(weight * sell, 2), 2))

    def test_a_duplex_pair_counts_both_springs_and_both_cones(self):
        """A Duplex is two springs nested on one shaft position, so it carries
        a set of cones for the inner diameter and a set for the outer."""
        order = self._assembly([(0.2625, 3.75, 30.0), (0.1875, 6.0, 30.0)])
        cones = round(2 * (CONE_PRICES[3.75] + CONE_PRICES[6.0]), 2)
        weight = (self._weight(0.2625, 3.75, 30.0)
                  + self._weight(0.1875, 6.0, 30.0))
        steel = round(2 * weight * STEEL_COST_PER_LB, 2)

        self.assertEqual(order._aa_cart_cost()["cost"], round(cones + steel, 2))

    def test_two_assemblies_cost_twice_one(self):
        one = self._assembly([(0.2625, 3.75, 30.0)], qty=1)._aa_cart_cost()
        two = self._assembly([(0.2625, 3.75, 30.0)], qty=2)._aa_cart_cost()

        self.assertEqual(two["cost"], round(one["cost"] * 2, 2))

    def test_a_longer_spring_costs_more_steel(self):
        short = self._assembly([(0.2625, 3.75, 24.0)])._aa_cart_cost()["cost"]
        long = self._assembly([(0.2625, 3.75, 48.0)])._aa_cart_cost()["cost"]

        self.assertGreater(long, short)

    # --- the plastic filler ---------------------------------------------------

    def test_the_filler_costs_its_rate_a_foot(self):
        """One per spring, cut to that spring's own length, and the line's
        quantity IS feet. It is charged at cost already, so this is the same
        arithmetic the quote does."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})
        order.order_line = [(0, 0, {
            "product_id": self.filler.id, "product_uom_qty": 7.0,
            "price_unit": FILLER_PRICE_PER_FOOT, "discount": 0.0})]

        self.assertEqual(
            order._aa_cart_cost(),
            {"cost": round(7.0 * FILLER_PRICE_PER_FOOT, 2), "unpriced": 0})

    def test_the_filler_is_still_costed_when_the_steel_cost_is_missing(self):
        """It has nothing to do with the steel rate: it is a bought-in part at
        a known price per foot."""
        self.rate(0)
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "website_id": self.website.id})
        order.order_line = [(0, 0, {
            "product_id": self.filler.id, "product_uom_qty": 6.0,
            "price_unit": FILLER_PRICE_PER_FOOT, "discount": 0.0})]

        self.assertEqual(order._aa_cart_cost()["cost"],
                         round(6.0 * FILLER_PRICE_PER_FOOT, 2))

    # --- when it cannot be said ----------------------------------------------

    def test_no_steel_cost_set_means_the_spring_is_reported_uncosted(self):
        """NOT COSTED AT THE PRICE OF ITS CONES. That would look like a costed
        line and be out by a factor of ten."""
        self.rate(0)
        order = self._assembly([(0.2625, 3.75, 30.0)])

        self.assertEqual(order._aa_cart_cost(), {"cost": 0.0, "unpriced": 1})

    def test_a_steel_cost_that_is_not_a_number_is_treated_as_unset(self):
        self.rate("about a dollar")
        order = self._assembly([(0.2625, 3.75, 30.0)])

        self.assertEqual(order._aa_cart_cost(), {"cost": 0.0, "unpriced": 1})

    def test_a_deleted_setting_falls_back_to_the_shipped_figure(self):
        """Nothing a customer sees is priced from this rate, so a missing row
        is answered with the figure the module ships with rather than with a
        page that cannot add up."""
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "spring_engineering.steel_cost_per_lb")]).unlink()
        order = self._assembly([(0.2625, 3.75, 30.0)])
        cones = round(2 * CONE_PRICES[3.75], 2)
        steel = round(2 * self._weight(0.2625, 3.75, 30.0) * STEEL_COST_PER_LB, 2)

        self.assertEqual(order._aa_cart_cost()["cost"], round(cones + steel, 2))

    def test_a_spring_with_no_specification_is_reported_uncosted(self):
        """An assembly booked before the specification was stored has nothing
        to work from, and saying so is the honest answer."""
        order = self._assembly([(0.2625, 3.75, 30.0)], spec=False)

        self.assertEqual(order._aa_cart_cost(), {"cost": 0.0, "unpriced": 1})

    def test_an_inside_diameter_we_have_no_cone_price_for_is_uncosted(self):
        """One the calculator would have refused to quote in the first place."""
        order = self._assembly([(0.2625, 4.5, 30.0)])

        self.assertNotIn(4.5, CONE_PRICES, "the fixture wants an unknown ID")
        self.assertEqual(order._aa_cart_cost(), {"cost": 0.0, "unpriced": 1})

    # --- the setting ----------------------------------------------------------

    def test_the_rate_comes_from_the_setting_and_takes_effect_at_once(self):
        """Read fresh on every cart, like the sell rate, so a change in
        Settings does not wait for a restart."""
        order = self._assembly([(0.2625, 3.75, 30.0)])
        self.rate(0.81)
        cheap = order._aa_cart_cost()["cost"]
        self.rate(1.62)
        dear = order._aa_cart_cost()["cost"]
        cones = round(2 * CONE_PRICES[3.75], 2)

        self.assertEqual(round(dear - cones, 2), round((cheap - cones) * 2, 2))

    def test_the_settings_page_writes_the_rate(self):
        settings = self.env["res.config.settings"].create(
            {"spring_steel_cost_per_lb": 0.93})
        settings.execute()

        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(
                "spring_engineering.steel_cost_per_lb"), "0.93")
        self.assertEqual(
            self.env["sale.order"]._aa_steel_cost_per_lb(), 0.93)


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

    # --- folded away until asked for ------------------------------------------

    def test_the_figure_is_folded_away_until_it_is_clicked(self):
        """THE COUNTER IS OFTEN FACING THE CUSTOMER. The row is there, the
        figure is not: it takes a deliberate click, so turning the screen
        round does not show somebody what their own order costs us."""
        self.authenticate("admin", "admin")
        self._add(4)
        row = self._row(self.url_open("/shop/cart").text)

        # The amount and the note both sit inside collapsed containers, and
        # the button that opens them says so.
        self.assertRegex(
            row, r'class="collapse[^"]*"[^>]*id="aa_cart_cost_value"',
            "the amount is not inside a collapsed container")
        self.assertIn('aria-expanded="false"', row, row)
        self.assertIn('data-bs-toggle="collapse"', row, row)

        # NOT ONE OF THEM PRE-OPENED. Bootstrap shows a collapse that carries
        # the `show` class, and a cart that came back already expanded would
        # defeat the whole point.
        self.assertNotIn("collapse show", row, row)
        self.assertNotIn("show collapse", row, row)

    def test_the_row_says_nothing_at_all_until_it_is_opened(self):
        """NOT EVEN THE WORD "Cost" (owner, 2026-10-21). Naming it told the
        customer there was a cost to see, which is most of what we were
        trying not to say.

        READ AS A BROWSER WOULD PAINT IT: the collapsed containers are cut
        out, then the tags, leaving the text that is actually on the screen
        before anybody clicks. There should be none of it.
        """
        self.authenticate("admin", "admin")
        self._add(4)
        row = self._row(self.url_open("/shop/cart").text)
        folded = re.sub(r'<div class="collapse.*?</div>\s*</td>', "</td>", row)
        folded = re.sub(r'<div class="collapse.*?</div>', "", folded)
        visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", folded)).strip()

        self.assertEqual(visible, "", "the row shows text before it is opened")

        # The name is still on the control for anyone who cannot see the
        # screen - and NOT as a `title`, which would paint a tooltip saying
        # "Cost" to whoever is looking at it.
        self.assertIn('aria-label="Cost, staff only"', row, row)
        self.assertNotIn("title=", row, row)

        # And the word is there once the fold is open, so the figure is named
        # rather than being a loose number under the Total.
        self.assertIn("Cost", row, row)

    def test_the_caret_never_fades_away(self):
        """IT USED TO FADE IN ON HOVER (owner, 2026-10-21: stop that). The
        employee had to reach for a control that was not visibly there, and a
        touch screen has no hover to reach with, so the caret is painted at
        rest instead. Nothing is given away by it: the caret is bare, the
        figure is still behind the fold, and the row only exists on a page
        served to an internal user.

        The stylesheet is what decides this, so it is what is checked - the
        class has to stay on the button for it to reach, and no rule may put
        the caret back behind a hover or a transparency."""
        css = open(
            "/home/odoo/src/user/spring_engineering/static/src/css/"
            "cart_included.css", encoding="utf-8").read()
        self.authenticate("admin", "admin")
        self._add(4)
        row = self._row(self.url_open("/shop/cart").text)

        self.assertIn("o_aa_cost_toggle", row, row)
        self.assertIn(".o_aa_cart_cost .o_aa_cost_toggle", css)

        # Not transparent, and not conditional on the mouse being anywhere.
        self.assertNotIn("opacity: 0;", css)
        self.assertNotIn(":hover", css)
        self.assertNotIn("hover: none", css)

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

    def test_a_spring_from_the_calculator_shows_a_cost_on_the_cart(self):
        """THE WHOLE PATH A MEMBER OF STAFF TAKES, not a crafted line: the
        calculator's own route books the assembly, and the cart page has to
        show a worked-out cost for it rather than "no cost set"."""
        self.authenticate("admin", "admin")
        answer = self.url_open(
            "/spring-calculator/add-to-cart",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "spec": {
                    "assembly": "Duplex", "springs": 2,
                    "springsSpec": [
                        {"role": "Outer", "wire": 0.2625, "id": 6,
                         "length": 32.25},
                        {"role": "Inner", "wire": 0.2253, "id": 3.75,
                         "length": 31.25}],
                    "doorWeight": 355, "doorHeight": "7' 0\"",
                    "cycles": 25000}}}),
            headers={"Content-Type": "application/json"})
        self.assertNotIn("error", answer.json().get("result", {}),
                         answer.json())

        line = self.env["sale.order.line"].sudo().search(
            [("spring_spec_json", "!=", False)], order="id desc", limit=1)
        self.assertTrue(line, "the route booked no spring")

        worked_out = line.order_id.sudo()._aa_cart_cost()
        row = self._row(self.url_open("/shop/cart").text)

        self.assertTrue(row, "no cost row for an order holding a spring")
        self.assertNotIn("no cost set", row, row)
        self.assertGreater(worked_out["cost"], 0.0, "the spring costed as zero")
        self.assertIn("%.2f" % worked_out["cost"], row, row)
        self.assertLess(worked_out["cost"], line.price_subtotal,
                        "a spring cannot cost what it sells for")

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
