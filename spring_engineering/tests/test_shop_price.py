"""THE PRICE ON THE SHOP PAGE AND THE PRICE ON THE PRODUCT PAGE ARE THE SAME.

Owner, 2026-10-28: *"kit prices aren't matching, for example the aa-1200
hardware kit says 254.39 when you first see it on the shop page, but when you
enter its product page it says 293.97 on its default values."*

HE IS RIGHT, AND IT IS ODOO'S OWN BEHAVIOUR. The two come from different
places:

  * the SHOP GRID calls `_get_sales_prices`, which prices the TEMPLATE -
    `pricelist._compute_price_rule(template, 1)` - with no combination at all,
    so no attribute extra is in it;
  * the PRODUCT PAGE calls `_get_combination_info`, which with no combination
    given picks `_get_first_possible_combination()` and prices THAT variant,
    extras included.

So a catalogue where the default variant carries an extra shows two different
numbers for the same product, and the customer meets the second one after
clicking. Since the 2026-10-21 merge nearly every family here is priced that
way - "the merge prices a variant as the product's price plus an extra per
size" - so this is not one kit, it is most of the shop.

Fetched off his live site while diagnosing: the grid said 254.39 and the page
said 293.97, a difference of 39.58.
"""

import re

from odoo.tests.common import HttpCase, tagged

EXTRA = 39.58
BASE = 254.39


@tagged("post_install", "-at_install")
class ShopGridPriceCase(HttpCase):
    """FETCHED, NOT CALLED.

    `_get_sales_prices` reads `request.pricelist`, and under `MockRequest`
    that comes back as a Mock which Odoo immediately subscripts - the same
    trap the custom kit's `_get_combination_info` fell into. Both numbers are
    therefore read off the rendered pages, which is also where he read them.
    """

    #: What the shop card prints, and what the product page prints for
    #: `combination_info['price']` - the two numbers he compared.
    CARD = re.compile(r'oe_currency_value">\s*([0-9,]+\.[0-9]{2})')
    PAGE = re.compile(
        r"combination_info\[&#39;price&#39;\][^>]*>[^<]*"
        r'<span class="oe_currency_value">\s*([0-9,]+\.[0-9]{2})')

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)

    def _product(self, extra_on_first=0.0, base=BASE, name=None):
        # UNIQUE NAMES. The shop is searched BY NAME to get a grid with one
        # card on it, so two fixtures called the same thing put two cards
        # there and the first one answers for both - which is how this file
        # first "proved" that a cheaper default was chosen.
        self.made = getattr(self, "made", 0) + 1
        name = name or "AAKitUnderTest%d" % self.made
        attribute = self.env["product.attribute"].create({
            "name": "Panels",
            "create_variant": "always",
            "value_ids": [(0, 0, {"name": "4 Panel"}),
                          (0, 0, {"name": "5 Panel"})],
        })
        template = self.env["product.template"].create({
            "name": name,
            "type": "consu",
            "list_price": base,
            "is_published": True,
            "attribute_line_ids": [(0, 0, {
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, attribute.value_ids.ids)],
            })],
        })

        if extra_on_first:
            template.attribute_line_ids.product_template_value_ids[0].price_extra = (
                extra_on_first)

        return template

    def _money(self, pattern, html, what):
        found = pattern.search(html)
        self.assertTrue(found, "no price found on the %s" % what)

        return float(found.group(1).replace(",", ""))

    def _prices(self, template):
        """(what the shop grid shows, what the product page shows)."""
        shop = self.url_open("/shop?search=%s" % template.name.replace(" ", "+"))
        page = self.url_open(template.website_url)

        self.assertEqual(shop.status_code, 200)
        self.assertEqual(page.status_code, 200)

        return (self._money(self.CARD, shop.text, "shop grid"),
                self._money(self.PAGE, page.text, "product page"))

    # --- the one he reported ----------------------------------------------

    def test_the_grid_shows_what_the_page_will_show(self):
        """THE ONE THAT SETTLES IT. A customer who reads 254.39 on the shop
        and 293.97 after one click has been told two different prices for the
        same thing, and the second one is the real one.

        COMPARED, NOT MEASURED. This database has a demo pricelist taking ten
        per cent off everything, so no absolute figure here would mean
        anything - and the fault is a DIFFERENCE between two screens, which
        survives any pricelist. Before the fix this read 228.95 against
        264.57, the same 39.58 gap he saw, discounted."""
        kit = self._product(extra_on_first=EXTRA)

        grid, page = self._prices(kit)

        self.assertAlmostEqual(grid, page, places=2)
        self.assertGreater(page, self._prices(self._product())[1],
                           "the extra is not in the page price either")

    def test_a_product_with_no_extras_is_untouched(self):
        """Most of the catalogue has no extra at all, and nothing about those
        may move - this is a fix for a difference, not a new price. They
        agreed before and they agree now, and `_get_sales_prices` is not even
        asked to do the work."""
        plain = self._product()

        grid, page = self._prices(plain)

        self.assertAlmostEqual(grid, page, places=2)
        self.assertFalse(plain._aa_has_priced_attributes())

    def test_a_product_with_no_variants_is_untouched(self):
        simple = self.env["product.template"].create({
            "name": "A hinge", "type": "consu", "list_price": 2.4,
            "is_published": True})

        grid, page = self._prices(simple)

        self.assertAlmostEqual(grid, page, places=2)
        self.assertFalse(simple._aa_has_priced_attributes())

    def test_the_extra_follows_the_default_and_not_the_cheapest(self):
        """The page prices the FIRST possible combination, so the grid has to
        do the same - not the lowest of them. Whatever the customer will be
        shown on arrival is what the card has to say."""
        kit = self._product()
        values = kit.attribute_line_ids.product_template_value_ids
        values[0].price_extra = 10.0
        values[1].price_extra = 1.0

        cheap_first = self._product()
        cheap_values = cheap_first.attribute_line_ids.product_template_value_ids
        cheap_values[0].price_extra = 1.0
        cheap_values[1].price_extra = 10.0

        grid, page = self._prices(kit)
        other_grid, _other_page = self._prices(cheap_first)

        self.assertAlmostEqual(grid, page, places=2)
        self.assertGreater(
            grid, other_grid,
            "the card took the cheapest combination rather than the one the"
            " page will open on")
