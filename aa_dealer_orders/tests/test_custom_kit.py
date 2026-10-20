"""THE CUSTOM KIT: a kit the customer puts together themselves.

The owner, 2026-10-20: "customer can decide almost everything and can add and
remove things from their kit, no spring, tracks, or cables will be in the kit
... the trims will be included ... it should basically work like the other
kits we have just with more options so that we can serve customers that want
doors that we dont have kits for."

Four decisions he made when asked: the page starts from an existing kit and is
then changed; colour is PER PART; only products ticked "Offer in Custom Kit"
may be chosen; and the parts add up, one order line each.
"""

import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class CustomKitCase(HttpCase):

    def setUp(self):
        super().setUp()
        self.kit = self.env.ref("aa_dealer_orders.product_custom_kit")
        self.category = self.env["product.category"].create({"name": "Hinges"})

        # A part that comes in two finishes, as a real variant pair.
        finish = self.env["product.attribute"].create({
            "name": "Finish Color", "create_variant": "always",
            "value_ids": [(0, 0, {"name": "White"}), (0, 0, {"name": "Black"})],
        })
        self.hinge = self.env["product.template"].create({
            "name": "11ga #8 Hinge", "default_code": "CH1411-8",
            "type": "consu", "is_storable": True, "list_price": 1.85,
            "categ_id": self.category.id, "is_published": True,
            "aa_custom_kit_part": True,
            "attribute_line_ids": [(0, 0, {
                "attribute_id": finish.id,
                "value_ids": [(6, 0, finish.value_ids.ids)]})],
        })
        # A part with one finish only.
        self.bracket = self.env["product.template"].create({
            "name": "J-10 Jamb Bracket", "default_code": "ATL-610J10JBBR",
            "type": "consu", "is_storable": True, "list_price": 2.10,
            "categ_id": self.category.id, "is_published": True,
            "aa_custom_kit_part": True,
        })
        # Ticked but not offerable: sized from a door, never in a custom kit.
        self.cable = self.env["product.template"].create({
            "name": '1/8" 7x19 Lift Cable', "type": "consu",
            "list_price": 9.0, "aa_custom_kit_part": True})
        # Not ticked at all.
        self.secret = self.env["product.template"].create({
            "name": "Shop Only Widget", "type": "consu", "list_price": 99.0})

    def _white_hinge(self):
        return self.hinge.product_variant_ids.filtered(
            lambda v: "White" in v.product_template_attribute_value_ids.mapped("name"))[:1]

    def _payload(self):
        return json.loads(self.kit._aa_custom_kit_json())

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, route)

        return response.json().get("result") or {}

    # --- the product itself ---------------------------------------------------

    def test_the_custom_kit_exists_and_is_a_kit(self):
        """"it should basically work like the other kits we have". The word
        kit in the name is what the rest of the shop keys off."""
        from odoo.addons.aa_shop_floor.models.sale_order import is_hardware_kit

        self.assertTrue(self.kit.aa_custom_kit)
        self.assertTrue(self.kit.is_published)
        self.assertTrue(is_hardware_kit(self.kit.product_variant_ids[:1]),
                        "the Hardware station would not pack it")

    def test_it_carries_no_price_of_its_own(self):
        """The parts carry the money, one line each (owner's choice). A price
        here would be charged on top of them."""
        self.assertEqual(self.kit.list_price, 0.0)

    def test_the_trims_option_is_on_it(self):
        """"the trims will be included" - the same Plastic Trims option every
        other kit carries, attached by name."""
        attributes = self.kit.attribute_line_ids.attribute_id.mapped("name")
        self.assertIn("Plastic Trims", attributes)

    # --- what may be put in it -------------------------------------------------

    def test_only_ticked_parts_are_offered(self):
        names = [part["name"] for part in self._payload()["parts"]]

        self.assertIn("11ga #8 Hinge", names)
        self.assertIn("J-10 Jamb Bracket", names)
        self.assertNotIn("Shop Only Widget", names, "it was never ticked")

    def test_springs_tracks_and_cables_are_never_offered(self):
        """Sized from a door and sold against one. A custom kit exists because
        the door is not one we have a kit for, so the page does not offer
        them - whatever anybody ticks."""
        names = [part["name"] for part in self._payload()["parts"]]
        self.assertNotIn('1/8" 7x19 Lift Cable', names)

    def test_a_part_is_offered_in_the_colours_it_actually_has(self):
        """PER PART (owner's choice). A part with a finish attribute offers
        its colours; one without is offered as the product it is."""
        parts = {part["name"]: part for part in self._payload()["parts"]}

        hinge_colours = sorted(c["label"] for c in parts["11ga #8 Hinge"]["colours"])
        self.assertEqual(hinge_colours, ["Black", "White"])
        self.assertEqual(len(parts["J-10 Jamb Bracket"]["colours"]), 1)

    # --- one list per category --------------------------------------------------

    def _shaft(self):
        """A part on a different shelf, so there is something to split."""
        shafts = self.env["product.category"].create({"name": "Shafts"})

        return self.env["product.template"].create({
            "name": '1" Steel Shaft', "default_code": "SHF-1",
            "type": "consu", "is_storable": True, "list_price": 24.0,
            "categ_id": shafts.id, "is_published": True,
            "aa_custom_kit_part": True})

    def test_each_part_says_which_category_it_is_in(self):
        """WHAT THE SPLITTING IS DONE ON (owner, 2026-10-20: "one list for
        hinges, one for shafts"). The id groups and the name only labels,
        because two categories under different parents can share a name."""
        self._shaft()
        parts = {part["name"]: part for part in self._payload()["parts"]}

        self.assertEqual(parts['1" Steel Shaft']["category"], "Shafts")
        self.assertEqual(parts["11ga #8 Hinge"]["category"], "Hinges")
        self.assertNotEqual(parts['1" Steel Shaft']["category_id"],
                            parts["11ga #8 Hinge"]["category_id"])

    def test_the_page_is_given_the_parts_under_their_own_categories(self):
        """What the shelves are built from, read off the page itself: the data
        the builder groups by has to reach it, and reach it per category.

        A REAL BROWSER WOULD BE BETTER and I wrote that test first - open
        Hinges, assert no shaft is on the shelf. Chrome cannot start in this
        container ("can't start new thread"), so it would have been a test that
        never ran. This asserts the contract the page depends on; the grouping
        itself is asserted below, off the script.
        """
        self._shaft()
        page = self.url_open(self.kit.website_url).text
        data = json.loads(page.split('data-kit="')[1].split('"')[0]
                          .replace("&#34;", '"').replace("&quot;", '"'))
        shelves = {}

        for part in data["parts"]:
            shelves.setdefault(part["category"], []).append(part["name"])

        self.assertIn("Hinges", shelves)
        self.assertIn("Shafts", shelves)
        self.assertNotIn('1" Steel Shaft', shelves["Hinges"],
                         "a shaft is on the hinge shelf")

    def test_the_builder_has_no_one_giant_list_left(self):
        """THE CHANGE THE OWNER ASKED FOR, 2026-10-20: "Instead of having every
        product in one list, can we split them up into categories ... That way
        the customer wont have to scroll through a giant list".

        What was there was a single "Add a part…" dropdown holding the whole
        catalogue. This asserts it is gone and that what replaced it is built
        per category - the one thing a source check can honestly hold on to
        while this container cannot run a browser.
        """
        from odoo.tools.misc import file_path

        with open(file_path(
                "aa_dealer_orders/static/src/js/custom_kit.js")) as handle:
            source = handle.read()

        self.assertNotIn("Add a part", source, "the giant dropdown is still there")
        self.assertIn("get categories()", source)
        self.assertIn("o_aa_custom_category", source)

    # --- starting from a kit that exists ---------------------------------------

    def test_an_existing_kit_offers_its_real_contents_to_start_from(self):
        """READ OFF THE KIT'S OWN PHANTOM BoM, which is what the picker takes
        out of stock for it today."""
        base = self.env["product.template"].create({
            "name": "AA 1200 Hardware Kit", "type": "consu",
            "is_storable": True, "aa_dealer_quick_order": True})
        variant = base.product_variant_ids[:1]
        self.env["mrp.bom"].create({
            "product_tmpl_id": base.id, "product_id": variant.id,
            "type": "phantom", "product_qty": 1.0,
            "bom_line_ids": [
                (0, 0, {"product_id": self._white_hinge().id, "product_qty": 4}),
                (0, 0, {"product_id": self.cable.product_variant_ids[:1].id,
                        "product_qty": 2}),
            ],
        })

        bases = {b["name"]: b for b in self._payload()["bases"]}
        self.assertIn("AA 1200 Hardware Kit", bases)
        parts = bases["AA 1200 Hardware Kit"]["parts"]

        self.assertEqual(parts.get(str(self._white_hinge().id)), 4.0)
        self.assertNotIn(str(self.cable.product_variant_ids[:1].id), parts,
                         "a cable came along from the base kit")

    def test_the_custom_kit_is_not_offered_as_its_own_base(self):
        self.assertNotIn(self.kit.name,
                         [b["name"] for b in self._payload()["bases"]])

    # --- building one, and putting it in a cart --------------------------------

    def _build(self, parts):
        return self._rpc("/aa/custom-kit/price",
                         {"template_id": self.kit.id, "parts": parts, "qty": 1})

    def test_the_page_prices_what_is_in_the_kit(self):
        priced = self._build([
            {"variant_id": self._white_hinge().id, "quantity": 4},
            {"variant_id": self.bracket.product_variant_ids[:1].id, "quantity": 8},
        ])

        self.assertEqual(priced["count"], 2)
        # ADDED UP FROM ITS OWN ROWS rather than from the list prices: this
        # shop has a pricelist, and my first version of this test asserted
        # 24.20 against a 10% discounted 21.78. What the page owes is that its
        # total is the sum of the lines it is showing.
        self.assertAlmostEqual(
            priced["total"],
            sum(row["price"] for row in priced["parts"]), places=2)
        self.assertGreater(priced["total"], 0.0)

    def test_a_part_nobody_offered_cannot_be_priced_or_bought(self):
        """The list comes from a browser, so it is checked against what is
        offered rather than against what was sent."""
        priced = self._build([
            {"variant_id": self.secret.product_variant_ids[:1].id, "quantity": 1},
        ])

        self.assertEqual(priced["count"], 0)
        self.assertEqual(priced["total"], 0.0)

    def test_the_parts_reach_the_cart_as_their_own_lines(self):
        """THE WHOLE SHAPE OF IT: the kit line is a heading and each part is a
        line of its own, hung off it - exactly how Springs, Tracks and Cables
        already reach a cart from the ordinary kit page."""
        hinge = self._white_hinge()
        bracket = self.bracket.product_variant_ids[:1]
        self._build([
            {"variant_id": hinge.id, "quantity": 4},
            {"variant_id": bracket.id, "quantity": 8},
        ])
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
        })

        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        self.assertTrue(order, "the kit never reached a cart")
        kit_line = order.order_line.filtered(
            lambda line: line.product_id.product_tmpl_id == self.kit)[:1]
        parts = order.order_line.filtered(
            lambda line: line.linked_line_id == kit_line)

        self.assertEqual(len(parts), 2, "the parts did not come with it")
        self.assertEqual(
            {(line.product_id, line.product_uom_qty) for line in parts},
            {(hinge, 4.0), (bracket, 8.0)})
        # WHAT THE PAGE SAID IS WHAT THE CART CHARGES, which is the figure
        # worth holding: both go through the same pricelist.
        priced = self._build([
            {"variant_id": hinge.id, "quantity": 4},
            {"variant_id": bracket.id, "quantity": 8},
        ])
        self.assertAlmostEqual(sum(parts.mapped("price_subtotal")),
                               priced["total"], places=2)

    def test_two_kits_bring_twice_the_parts(self):
        hinge = self._white_hinge()
        self._build([{"variant_id": hinge.id, "quantity": 4}])
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 2,
        })

        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        part = order.order_line.filtered(lambda line: line.product_id == hinge)[:1]

        self.assertEqual(part.product_uom_qty, 8.0)

    def test_an_empty_kit_adds_nothing_but_itself(self):
        self._build([])
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
        })

        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        kit_line = order.order_line.filtered(
            lambda line: line.product_id.product_tmpl_id == self.kit)[:1]

        self.assertTrue(kit_line)
        self.assertFalse(order.order_line.filtered(
            lambda line: line.linked_line_id == kit_line))

    def test_a_silly_quantity_is_refused(self):
        hinge = self._white_hinge()
        priced = self._build([{"variant_id": hinge.id, "quantity": 100000}])

        self.assertEqual(priced["count"], 0, "an unbounded quantity got through")

    # --- and the page it is all shown on ---------------------------------------

    def test_the_product_page_carries_the_builder(self):
        page = self.url_open(self.kit.website_url).text

        self.assertIn('id="aa_custom_kit"', page)
        self.assertIn("11ga #8 Hinge", page, "the parts did not reach the page")

    # --- ticking it on a lot of products at once --------------------------------

    def _product_view(self, view, mode):
        from lxml import etree

        return etree.fromstring(self.env["product.template"].get_view(
            self.env.ref(view).id, mode)["arch"])

    def test_the_tick_is_a_column_of_the_product_list(self):
        """HOW SEVERAL PRODUCTS GET TICKED AT ONCE (owner, 2026-10-20: "how do
        i mass select products to put them on the kit").

        Odoo's answer is list-view multi-edit, and it only offers to update the
        other selected records for a field that is IN THE LIST. The tick was on
        the form only, so selecting fifty hinges got you nowhere. This asserts
        the column, which is the whole mechanism.
        """
        arch = self._product_view("product.product_template_tree_view", "list")
        column = arch.xpath("//field[@name='aa_custom_kit_part']")

        self.assertTrue(column, "no column, so no multi-edit")
        self.assertEqual(column[0].get("optional"), "hide",
                         "it should be off until it is wanted")

    def test_the_tick_on_the_form_is_labelled(self):
        """THE BUG THIS GUARDS: group[@name='sale'] is a container OF GROUPS, so
        a bare field dropped in it rendered as an unlabelled checkbox - "two
        random boxes in the ecommerce media section" (owner, 2026-10-20)."""
        arch = self._product_view("product.product_template_form_view", "form")
        field = arch.xpath("//field[@name='aa_custom_kit_part']")

        self.assertTrue(field, "the tick is not on the product form")
        self.assertEqual(
            field[0].getparent().get("string"), "AA Impact",
            "it is not inside a titled group, so it renders without a label")

    def test_a_filter_finds_the_ones_already_ticked(self):
        arch = self._product_view("product.product_template_search_view", "search")

        self.assertTrue(arch.xpath("//filter[@name='aa_custom_kit_part']"))

    def test_ticking_many_at_once_offers_them_all(self):
        """What multi-edit does under the covers: one write over the selection."""
        chosen = self.secret | self.env["product.template"].create({
            "name": "Second Widget", "type": "consu", "list_price": 4.0})
        chosen.write({"aa_custom_kit_part": True})

        names = [part["name"] for part in self._payload()["parts"]]
        self.assertIn("Shop Only Widget", names)
        self.assertIn("Second Widget", names)

    def test_the_builder_starts_itself_on_an_already_loaded_page(self):
        """THE BUG THIS GUARDS, 2026-10-20: the owner ticked a part, the data
        reached the page - the test above proved that much - and the builder
        never appeared, because the script only LISTENED for DOMContentLoaded.

        The frontend bundle is loaded lazily, after that event has been and
        gone, so the listener never fired and the div kept the d-none it ships
        with. The test above could not catch it: it proved the data arrived,
        not that anything used it. kit_page.js has always handled this; this
        asserts the one line that matters is in both.
        """
        from odoo.tools.misc import file_path

        for name in ("custom_kit.js", "kit_page.js"):
            with open(file_path(
                    "aa_dealer_orders/static/src/js/%s" % name)) as handle:
                source = handle.read()

            with self.subTest(script=name):
                self.assertIn('readyState', source,
                              "it only waits for an event that may have passed")
