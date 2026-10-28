import json

from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConfiguredPriceSurvivesCheckout(TransactionCase):
    """A made-to-order assembly must not become free at the payment screen."""

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Checkout Test"})
        self.order = self.env["sale.order"].create({"partner_id": self.partner.id})

    def _line(self, product, price):
        line = self.env["sale.order.line"].create({
            "order_id": self.order.id,
            "product_id": product.id,
            "product_uom_qty": 1,
            "name": "Custom Torsion Spring Assembly",
        })
        line.write({"price_unit": price})

        return line

    def test_the_spring_keeps_its_price_when_prices_are_recomputed(self):
        """THE BUG: 342.56 at the cart, 0.00 at the payment screen.

        _recompute_prices runs when the pricelist changes, and the pricelist
        resolves late in checkout once the partner is known. It recomputes
        price_unit with force_price_recomputation, which overrides even a
        price written by hand, and this product deliberately lists at zero.
        The customer could then pay nothing for a made-to-order assembly, and
        every page after that showed zero too.
        """
        spring = self.env.ref(
            "spring_engineering.product_custom_spring").product_variant_id
        line = self._line(spring, 342.56)
        self.assertEqual(spring.list_price, 0.0, "the product should list at 0")

        self.order._recompute_prices()
        line.invalidate_recordset()

        self.assertEqual(line.price_unit, 342.56, "the assembly became free")

    def test_the_filler_keeps_its_price_too(self):
        """It is priced the same way and lists at zero the same way."""
        filler = self.env.ref(
            "spring_engineering.product_custom_filler").product_variant_id
        line = self._line(filler, 19.44)
        self.order._recompute_prices()
        line.invalidate_recordset()
        self.assertEqual(line.price_unit, 19.44)

    def test_an_ordinary_product_is_still_repriced(self):
        """THE OTHER HALF, and the one a careless fix would break.

        Excluding every line from the recomputation would pass the test above
        and quietly stop pricelists working for the whole shop. An ordinary
        product whose price was tampered with must still be put back.
        """
        ordinary = self.env["product.product"].create({
            "name": "An Ordinary Bracket", "type": "consu", "list_price": 100.0})
        line = self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": ordinary.id,
            "product_uom_qty": 1})
        # WHAT THE PRICELIST SAYS, read rather than assumed. Writing 100.0 here
        # was my first attempt and it failed at 90.0, because the pricelist in
        # this database takes 10% off - the repricing was working and the test
        # was wrong. Capturing the computed price first asserts the behaviour
        # instead of a number I guessed.
        priced = line.price_unit
        self.assertGreater(priced, 0.0)

        line.write({"price_unit": 5.0})
        self.order._recompute_prices()
        line.invalidate_recordset()

        self.assertEqual(
            line.price_unit, priced,
            "ordinary lines stopped being repriced - pricelists are broken")

    def test_the_two_kinds_of_line_coexist(self):
        """One order with both: the assembly holds, the bracket is repriced."""
        spring = self.env.ref(
            "spring_engineering.product_custom_spring").product_variant_id
        ordinary = self.env["product.product"].create({
            "name": "Another Bracket", "type": "consu", "list_price": 42.0})
        configured = self._line(spring, 300.0)
        plain = self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": ordinary.id,
            "product_uom_qty": 1})
        priced = plain.price_unit
        plain.write({"price_unit": 1.0})

        self.order._recompute_prices()
        (configured | plain).invalidate_recordset()

        self.assertEqual(configured.price_unit, 300.0, "the assembly was reset")
        self.assertEqual(plain.price_unit, priced, "the bracket was not repriced")


@tagged("post_install", "-at_install")
class TestConfiguredPriceFromTheRoute(HttpCase):
    """The same thing along the path a customer actually takes."""

    def test_a_quoted_assembly_survives_a_price_recomputation(self):
        # SINGLE, not the Duplex this used to send: a duplex is no longer
        # sold (owner, 2026-10-28) and the route refuses it. What is under
        # test is that a quoted price survives a recomputation, which is the
        # same question whichever assembly carries it.
        payload = {"jsonrpc": "2.0", "method": "call", "params": {"spec": {
            "assembly": "Single", "springs": 2,
            "springsSpec": [
                {"role": "Spring", "wire": 0.2625, "id": 6, "length": 32.25}],
            "doorWeight": 355, "doorHeight": "7' 0\"", "cycles": 25000}}}
        response = self.url_open(
            "/spring-calculator/add-to-cart", data=json.dumps(payload),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", response.json().get("result", {}))

        line = self.env["sale.order.line"].search(
            [("name", "like", "Custom Torsion Spring Assembly")],
            order="id desc", limit=1)
        self.assertTrue(line)
        quoted = line.price_unit
        self.assertGreater(quoted, 0, "the route booked a free assembly")

        line.order_id._recompute_prices()
        line.invalidate_recordset()

        self.assertEqual(
            line.price_unit, quoted,
            "the quoted price did not survive checkout")
