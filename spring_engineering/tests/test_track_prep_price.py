from odoo.addons.website_sale.tests.common import MockRequest
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPreparedTrackPrice(TransactionCase):
    """The shop page has to quote what the cart will charge.

    Picking Prepared adds a flag angle and a graduated set of jamb brackets,
    each a real product on its own line. The attribute carries no price of its
    own, so the product page went on showing the bare track's price and the
    total only grew once the customer reached the cart - a surprise charge,
    which is the one thing a price on a product page must not be.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.attr = self.env.ref("spring_engineering.attribute_track_preparation")
        self.v_unprepared = self.env.ref(
            "spring_engineering.attribute_value_track_unprepared")
        self.v_prepared = self.env.ref(
            "spring_engineering.attribute_value_track_prepared")

        self.brackets = {}

        for size, code in [("10", "ATL-610J10JBBR"), ("12", "ATL-614J12JBBR"),
                           ("14", "ATL-616J14JBBR"), ("16", "ATL-616J16JBBR")]:
            found = self.env["product.product"].search(
                [("default_code", "=", code)], limit=1)
            self.assertTrue(found, "catalogue bracket %s is missing" % code)
            self.brackets[size] = found

        def flag(name, price):
            found = self.env["product.product"].search(
                [("name", "=ilike", name)], limit=1)

            if found:
                return found

            return self.env["product.template"].create({
                "name": name, "type": "consu", "list_price": price,
            }).product_variant_id

        self.flag_black = flag("Flag Angle Black", 7.5)

        # NO TAXES ANYWHERE, so the figure on the page, the untaxed total and
        # the total are the same number and a tax setting cannot make this test
        # pass or fail for the wrong reason.
        parts = self.flag_black
        for bracket in self.brackets.values():
            parts |= bracket
        parts.product_tmpl_id.write({"taxes_id": [(5,)]})
        self.parts = parts

        self.partner = self.env["res.partner"].create({"name": "Test Buyer"})

    def _track(self, name="CH-VT-2-2 Vertical Track 76-7 door height black"):
        tmpl = self.env["product.template"].create({
            "name": name, "type": "consu", "list_price": 42.0,
            "is_published": True, "taxes_id": [(5,)],
        })
        self.env["product.template.attribute.line"].create({
            "product_tmpl_id": tmpl.id, "attribute_id": self.attr.id,
            "value_ids": [(6, 0, [self.v_unprepared.id, self.v_prepared.id])]})
        tmpl.invalidate_recordset()

        return tmpl

    def _ptav(self, tmpl, name):
        return tmpl.attribute_line_ids.filtered(
            lambda l: l.attribute_id == self.attr
        ).product_template_value_ids.filtered(lambda p: p.name == name)

    def _page_price(self, tmpl, choice, qty=1):
        """The price the shop page shows for this choice."""
        with MockRequest(self.env, website=self.website):
            info = tmpl._get_combination_info(
                combination=self._ptav(tmpl, choice),
                product_id=tmpl.product_variant_id.id,
                add_qty=qty,
            )

        return info["price"]

    def _part_price(self, product, qty):
        """What the shop would charge for one of these parts."""
        with MockRequest(self.env, website=self.website):
            return product.product_tmpl_id._get_combination_info(
                product_id=product.id, add_qty=qty)["price"]

    def _parts_total(self):
        """4 x #10, 4 x #12, 4 x #14 and one flag angle: a 7 ft door.

        AT SHOP PRICES, not list prices: the website's pricelist discounts
        this catalogue, and the page has to agree with the cart rather than
        with the product form.
        """
        return (4 * self._part_price(self.brackets["10"], 4)
                + 4 * self._part_price(self.brackets["12"], 4)
                + 4 * self._part_price(self.brackets["14"], 4)
                + 1 * self._part_price(self.flag_black, 1))

    def _bare_price(self, tmpl):
        """The track's own price, with none of this module's arithmetic."""
        with MockRequest(self.env, website=self.website):
            return tmpl.with_context(track_prep_no_extra=True)._get_combination_info(
                combination=self._ptav(tmpl, "Prepared"),
                product_id=tmpl.product_variant_id.id)["price"]

    def test_unprepared_is_the_bare_track(self):
        tmpl = self._track()
        self.assertEqual(self._page_price(tmpl, "Unprepared"),
                         self._bare_price(tmpl))

    def test_prepared_shows_the_parts_it_will_add(self):
        """THE BUG: this used to be the bare price, and the cart charged more."""
        tmpl = self._track()
        bare = self._bare_price(tmpl)
        parts = self._parts_total()
        self.assertGreater(parts, 0, "the parts are free, so this proves nothing")
        self.assertAlmostEqual(self._page_price(tmpl, "Prepared"), bare + parts,
                               places=2)

    def test_the_page_quotes_what_the_cart_charges(self):
        """The assertion that matters: one number, from both ends."""
        tmpl = self._track()
        quoted = self._page_price(tmpl, "Prepared")

        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        order._cart_add(
            tmpl.product_variant_id.id, 1,
            no_variant_attribute_value_ids=[self._ptav(tmpl, "Prepared").id])

        self.assertAlmostEqual(order.amount_total, quoted, places=2)

    def test_two_tracks_quote_the_price_of_one(self):
        """A product page shows a UNIT price, however many are being bought."""
        tmpl = self._track()
        one = self._page_price(tmpl, "Prepared", qty=1)
        self.assertAlmostEqual(self._page_price(tmpl, "Prepared", qty=2), one,
                               places=2)

        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        order._cart_add(
            tmpl.product_variant_id.id, 2,
            no_variant_attribute_value_ids=[self._ptav(tmpl, "Prepared").id])
        self.assertAlmostEqual(order.amount_total, one * 2, places=2)

    def test_a_taller_door_costs_more_to_prepare(self):
        """The mix is graduated, so the price has to follow the door."""
        short = self._page_price(self._track(
            "CH-VT-2-2 Vertical Track 76-7 door height black"), "Prepared")
        tall = self._page_price(self._track(
            "CH-VT-2-2 Vertical Track 180-15 door height black"), "Prepared")
        self.assertGreater(tall, short)

    def test_a_track_we_cannot_prepare_quotes_the_bare_price(self):
        """The cart adds nothing and says why, so the page must not add a
        price for parts that will never be billed."""
        unreadable = self._track("Vertical Track, no height in the name, black")
        self.assertEqual(self._page_price(unreadable, "Prepared"),
                         self._bare_price(unreadable))

        unknown_finish = self._track(
            "CH-VT-2-2 Vertical Track 76-7 door height brass")
        self.assertEqual(self._page_price(unknown_finish, "Prepared"),
                         self._bare_price(unknown_finish))

    def test_the_shop_grid_shows_the_bare_price(self):
        """/shop asks for the template alone, and nothing is picked there."""
        tmpl = self._track()

        with MockRequest(self.env, website=self.website):
            info = tmpl._get_combination_info(only_template=True)

        self.assertEqual(info["price"], self._page_price(tmpl, "Unprepared"))
        self.assertLess(info["price"], self._page_price(tmpl, "Prepared"))

    def test_an_ordinary_product_is_untouched(self):
        plain = self.env["product.template"].create({
            "name": "Ordinary Thing", "type": "consu", "list_price": 10.0,
            "taxes_id": [(5,)]})

        with MockRequest(self.env, website=self.website):
            self.assertEqual(
                plain._get_combination_info(
                    product_id=plain.product_variant_id.id)["price"],
                plain.with_context(track_prep_no_extra=True)._get_combination_info(
                    product_id=plain.product_variant_id.id)["price"])
