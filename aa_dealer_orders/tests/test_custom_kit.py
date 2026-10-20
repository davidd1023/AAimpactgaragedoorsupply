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

    # --- the same part in two colours, as two products -------------------------

    def _coloured_pair(self, stem="Cut Down Hinge"):
        """How this catalogue really holds a colour: two separate products."""
        return self.env["product.template"].create([{
            "name": "%s %s" % (stem, colour), "type": "consu",
            "is_storable": True, "list_price": 2.5,
            "categ_id": self.category.id, "is_published": True,
            "aa_custom_kit_part": True,
        } for colour in ("White", "Black")])

    def test_two_products_that_are_one_part_in_two_colours_become_one_row(self):
        """WHY THE COLOUR DROPDOWN NEVER APPEARED, 2026-10-20: "i dont see the
        color dropdown".

        It is offered when a part has more than one colour, and nothing in
        this catalogue has a finish ATTRIBUTE - a white hinge and a black
        hinge are two separate products with the colour in the name. So there
        was no part with two colours to offer, and the rows a kit fills itself
        with were the white ones.
        """
        white, black = self._coloured_pair()
        parts = {part["name"]: part for part in self._payload()["parts"]}

        self.assertIn("Cut Down Hinge", parts, "the pair was not recognised")
        self.assertNotIn("Cut Down Hinge White", parts, "it is still two rows")
        row = parts["Cut Down Hinge"]

        self.assertEqual(
            sorted((colour["label"], colour["id"]) for colour in row["colours"]),
            sorted([("White", white.product_variant_ids[:1].id),
                    ("Black", black.product_variant_ids[:1].id)]),
            "a colour has to point at its own product, or the cart books the "
            "wrong one")

    def test_a_colour_that_has_no_sibling_keeps_the_name_it_was_given(self):
        """A FAMILY OF ONE IS NEVER RENAMED. Nothing to switch to, so the
        product stays what the catalogue calls it - "Zinc Plated Bolt" does
        not become a "Plated Bolt" that comes in zinc."""
        self.env["product.template"].create({
            "name": "Zinc Plated Bolt", "type": "consu", "list_price": 0.4,
            "categ_id": self.category.id, "aa_custom_kit_part": True})
        parts = {part["name"]: part for part in self._payload()["parts"]}

        self.assertIn("Zinc Plated Bolt", parts)
        self.assertEqual(len(parts["Zinc Plated Bolt"]["colours"]), 1)
        self.assertEqual(parts["Zinc Plated Bolt"]["colours"][0]["label"], "")

    def test_a_two_word_finish_is_read_as_one_colour(self):
        """"Desert Tan" is a colour, not a tan one of something desert.

        The stem is deliberately a name no real product has: this runs against
        a live catalogue, and the first version used "End Bearing Plate",
        which a product already in the database was also called - so the
        family came out with a third colour and the test failed on data rather
        than on code.
        """
        for colour in ("Desert Tan", "White"):
            self.env["product.template"].create({
                "name": "Sudden Bearing Plate %s" % colour, "type": "consu",
                "list_price": 3.0, "categ_id": self.category.id,
                "aa_custom_kit_part": True})
        parts = {part["name"]: part for part in self._payload()["parts"]}

        self.assertIn("Sudden Bearing Plate", parts)
        self.assertEqual(
            sorted(colour["label"]
                   for colour in parts["Sudden Bearing Plate"]["colours"]),
            ["Desert Tan", "White"])

    def test_a_part_with_real_finish_variants_is_left_alone(self):
        """It already offers its own colours; it is not merged with anything
        that happens to be named similarly."""
        parts = {part["name"]: part for part in self._payload()["parts"]}

        self.assertIn("11ga #8 Hinge", parts)
        self.assertEqual(
            sorted(colour["label"] for colour in parts["11ga #8 Hinge"]["colours"]),
            ["Black", "White"])

    def test_a_kit_filled_from_a_base_can_be_moved_to_the_other_colour(self):
        """END TO END, the thing he asked for: a kit that fills itself with
        white parts, and a colour that moves them - because the white row and
        the black row are now one part with two colours."""
        white, black = self._coloured_pair()
        base = self.env["product.template"].create({
            "name": "AA 2000 Hardware Kit", "type": "consu",
            "is_storable": True, "aa_dealer_quick_order": True})
        self.env["mrp.bom"].create({
            "product_tmpl_id": base.id,
            "product_id": base.product_variant_ids[:1].id,
            "type": "phantom", "product_qty": 1.0,
            "bom_line_ids": [(0, 0, {
                "product_id": white.product_variant_ids[:1].id,
                "product_qty": 10})],
        })
        payload = self._payload()
        filled = {b["name"]: b for b in payload["bases"]}["AA 2000 Hardware Kit"]
        row = {part["name"]: part for part in payload["parts"]}["Cut Down Hinge"]

        # What the kit fills itself with is the white product...
        self.assertEqual(filled["parts"],
                         {str(white.product_variant_ids[:1].id): 10.0})
        # ...and the page knows which product the same part in black is.
        self.assertIn(black.product_variant_ids[:1].id,
                      [colour["id"] for colour in row["colours"]])

    # --- one list per category --------------------------------------------------

    def _shaft(self):
        """A part on a different shelf, so there is something to split."""
        shafts = self.env["product.category"].create({"name": "Shafts"})

        return self.env["product.template"].create({
            "name": '1" Steel Shaft', "default_code": "SHF-1",
            "type": "consu", "is_storable": True, "list_price": 24.0,
            "categ_id": shafts.id, "is_published": True,
            "aa_custom_kit_part": True})

    def _shelf_of(self, name):
        parts = {part["name"]: part for part in self._payload()["parts"]}

        return parts[name]["category"]

    def test_a_part_is_shelved_BY_ITS_SHOP_CATEGORY(self):
        """THE BUG THIS FIXES, 2026-10-20: "all the items i add to the kit are
        going into other parts, they each have categories that should be used".

        In Odoo 19 the internal Product Category is neither required nor
        defaulted - I checked the field, there is no `required=True` and no
        default - so a catalogue built through the website can have every
        product in no internal category at all, which put every ticked part on
        one "Other parts" shelf. The categories the owner means are the ones
        the shop is arranged by, so those are what shelve a part.
        """
        shop = self.env["product.public.category"].create({"name": "Hinges & Brackets"})
        part = self.env["product.template"].create({
            "name": "Shop Categorised Hinge", "type": "consu",
            "list_price": 3.0, "is_published": True,
            "aa_custom_kit_part": True,
            "public_categ_ids": [(6, 0, shop.ids)]})

        self.assertFalse(part.categ_id, "Odoo 19 gave it an internal category "
                                        "after all - this test is now moot")
        self.assertEqual(self._shelf_of("Shop Categorised Hinge"),
                         "Hinges & Brackets")

    def test_the_shop_category_wins_over_the_internal_one(self):
        """Both set: the shop's own arrangement is the one the customer knows."""
        shop = self.env["product.public.category"].create({"name": "Struts"})
        self.hinge.public_categ_ids = shop

        self.assertEqual(self._shelf_of("11ga #8 Hinge"), "Struts")

    def test_the_internal_category_shelves_a_part_with_no_shop_category(self):
        self.assertFalse(self.hinge.public_categ_ids)
        self.assertEqual(self._shelf_of("11ga #8 Hinge"), "Hinges")

    def test_a_part_with_no_category_anywhere_goes_on_other_parts(self):
        """Honestly labelled rather than invented. "All" counts as none: it is
        Odoo's root shelf, not a category anybody chose."""
        self.env["product.template"].create({
            "name": "Uncategorised Widget", "type": "consu", "list_price": 1.0,
            "aa_custom_kit_part": True})
        root = self.env["product.category"].search(
            [("parent_id", "=", False), ("name", "=", "All")], limit=1)
        self.env["product.template"].create({
            "name": "Widget In All", "type": "consu", "list_price": 1.0,
            "categ_id": root.id, "aa_custom_kit_part": True})

        self.assertEqual(self._shelf_of("Uncategorised Widget"), "Other parts")

        if root:
            self.assertEqual(self._shelf_of("Widget In All"), "Other parts")

    def test_two_shop_categories_shelve_a_part_once(self):
        """Under the one the shop itself puts first, so a part is in one place
        and the quantity on the page is the quantity in the kit."""
        first = self.env["product.public.category"].create(
            {"name": "Hinges", "sequence": 1})
        second = self.env["product.public.category"].create(
            {"name": "Zinc", "sequence": 9})
        self.bracket.public_categ_ids = first | second
        shelves = [part["category"] for part in self._payload()["parts"]
                   if part["name"] == "J-10 Jamb Bracket"]

        self.assertEqual(shelves, ["Hinges"])

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

    def test_the_trims_are_at_the_bottom_of_the_page(self):
        """THE ORDER ON THE PAGE (owner, 2026-10-20: "move the trims to the
        bottom"): build your kit, then the trims, then Add to Cart.

        Done by putting the builder in front of Odoo's attribute section
        rather than by moving that section down: it lives inside the
        add-to-cart form and carries the chosen trim with it.
        """
        page = self.url_open(self.kit.website_url).text
        builder = page.index('id="aa_custom_kit"')
        trims = page.index("o_wsale_product_details_content_section_attributes")
        cart = page.index("o_wsale_product_details_content_section_cta")

        self.assertLess(builder, trims, "the trims are above the builder")
        self.assertLess(trims, cart, "the trims are below Add to Cart")

    def _run_in_node(self, body):
        """The builder's own script, run as plain JavaScript.

        NOT A SUBSTITUTE FOR A BROWSER, and it does not pretend to be one: it
        loads custom_kit.js, makes a bare page object and calls the methods
        that are pure arithmetic over what is in the kit. Chrome cannot start
        in this container, and this is the part of the page that can still be
        tested rather than described.
        """
        import shutil
        import subprocess

        from odoo.tools.misc import file_path

        node = shutil.which("node")

        if not node:
            self.skipTest("node is not installed, so the page script cannot be run")

        script = """
            const fs = require("fs"), vm = require("vm"), assert = require("assert");
            const source = fs.readFileSync(process.argv[1], "utf8");
            const document = {
                readyState: "complete", getElementById: () => null,
                addEventListener: () => {}, querySelector: () => null,
            };
            const CustomKitPage = vm.runInNewContext(
                source + ";CustomKitPage", { document, fetch: () => {} });
            const page = (parts, chosen) => {
                const built = Object.create(CustomKitPage.prototype);
                Object.assign(built, {
                    data: { parts }, chosen: new Map(chosen), colour: "",
                    panels: [], offers: [],
                    rebuildShelves: () => {}, draw: () => {},
                });

                return built;
            };
            // JSON, NOT deepStrictEqual: the script runs in its own vm
            // context, so an array it builds has a different Array prototype
            // and a structural comparison fails on that alone.
            const inKit = (built, expected, why) => assert.strictEqual(
                JSON.stringify([...built.chosen]), JSON.stringify(expected), why);
            const HINGE = { name: "Hinge", colours: [
                { id: 1, label: "White" }, { id: 2, label: "Black" }] };
            const STRUT = { name: "Strut", colours: [
                { id: 3, label: "White" }, { id: 4, label: "Black" }] };
            const GALV = { name: "Galvanised shaft", colours: [{ id: 5, label: "" }] };
        """ + body + """
            console.log("ok");
        """
        done = subprocess.run(
            [node, "-e", script,
             file_path("aa_dealer_orders/static/src/js/custom_kit.js")],
            capture_output=True, text=True, timeout=60)

        self.assertEqual(done.returncode, 0,
                         "%s%s" % (done.stdout, done.stderr))

    def test_the_kit_colour_moves_every_part_that_comes_in_it(self):
        """THE CHANGE ASKED FOR, 2026-10-20: "the build your kit makes it so
        all items added are white so you should add an option to change the
        auto added products to a different color".

        Starting from an existing kit fills the rows from that kit's own parts
        list - white ones - so every automatic row came out white. One colour
        for the kit moves the lot, and leaves alone the parts that are not
        made in it.
        """
        self._run_in_node("""
            const kit = page([HINGE, STRUT, GALV], [[1, 4], [3, 2], [5, 1]]);
            kit.setColour("Black");
            inKit(kit, [[2, 4], [4, 2], [5, 1]],
                "the kit did not move to black (the shaft should not move)");

            // And what Add puts in from then on.
            assert.strictEqual(kit.variantFor(HINGE), 2);
            assert.strictEqual(kit.variantFor(GALV), 5,
                "a part that is not made in black was dragged out of the kit");

            // Back again, with nothing lost on the way.
            kit.setColour("White");
            inKit(kit, [[1, 4], [3, 2], [5, 1]], "it did not come back");
        """)

    def test_two_colours_of_one_part_add_up_when_the_kit_colour_moves(self):
        """Four white hinges and three black ones become seven black hinges,
        not three."""
        self._run_in_node("""
            const kit = page([HINGE], [[1, 4], [2, 3]]);
            kit.setColour("Black");
            inKit(kit, [[2, 7]], "the two colours did not add up");
        """)

    def test_the_colours_offered_are_the_ones_the_catalogue_sells(self):
        """Commonest first, and a part with no finish of its own is not a
        colour anybody can pick for the kit."""
        self._run_in_node("""
            const ONE_OFF = { name: "Almond latch", colours: [
                { id: 6, label: "White" }, { id: 7, label: "Almond" }] };
            const kit = page([HINGE, STRUT, GALV, ONE_OFF], []);
            assert.strictEqual(JSON.stringify(kit.colourLabels()),
                JSON.stringify(["White", "Black", "Almond"]));
        """)

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

    def test_the_popup_names_the_parts_that_went_in_with_the_kit(self):
        """THE FAULT THIS GUARDS, 2026-10-20: "when i put the kit into the
        cart, the only things that pop up are the kit at 1$ and a galvanized
        hinge #1 ... none of the items i added to the kit are getting added
        into the cart."

        They were going in - the cart held every one of them. Core builds the
        "added to your cart" popup out of the lines IT added and returns that
        with the response, and the parts are hung off the kit line afterwards,
        so the popup named the kit alone and read as if nothing else had been
        booked. The cart page was right; the popup was the liar.
        """
        hinge = self._white_hinge()
        bracket = self.bracket.product_variant_ids[:1]
        self._build([
            {"variant_id": hinge.id, "quantity": 4},
            {"variant_id": bracket.id, "quantity": 8},
        ])
        added = self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
        })
        shown = (added.get("notification_info") or {}).get("lines") or []
        headers = " ".join(line.get("name") or "" for line in shown)

        self.assertEqual(len(shown), 3,
                         "the popup shows %s of the 3 lines booked" % len(shown))
        self.assertIn("Custom Kit", headers)
        self.assertIn("11ga #8 Hinge", headers)
        self.assertIn("J-10 Jamb Bracket", headers)

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
