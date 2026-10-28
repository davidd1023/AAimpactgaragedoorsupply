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

from odoo.addons.http_routing.tests.common import MockRequest
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

    def _rpc(self, route, params, raw=False):
        """`raw` hands back the whole JSON-RPC envelope, errors included.

        The default swallows them, which is right for the calls that are
        expected to work - but a route that is SUPPOSED to refuse answers
        with a top-level `error` and no `result` at all, and a helper that
        returns {} for both cannot tell a refusal from an empty success.
        """
        response = self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, route)
        body = response.json()

        return body if raw else (body.get("result") or {})

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
            // `sandbox` stays reachable so a test can swap fetch for its own.
            const sandbox = { document, fetch: () => {} };
            const CustomKitPage = vm.runInNewContext(
                source + ";CustomKitPage", sandbox);
            const page = (parts, chosen) => {
                const built = Object.create(CustomKitPage.prototype);
                Object.assign(built, {
                    data: { parts }, chosen: new Map(chosen), colour: "",
                    panels: [], offers: [],
                    // The builder keeps the parts list on its own element,
                    // where the Add to Cart request picks it up.
                    root: { dataset: {} },
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
                { id: 1, label: "White", finish: "White" },
                { id: 2, label: "Black", finish: "Black" }] };
            const STRUT = { name: "Strut", colours: [
                { id: 3, label: "White", finish: "White" },
                { id: 4, label: "Black", finish: "Black" }] };
            const GALV = { name: "Galvanised shaft",
                colours: [{ id: 5, label: "", finish: "" }] };
            (async () => {
        """ + body + """
                console.log("ok");
            })().catch((error) => {
                console.error((error && error.message) || error);
                process.exit(1);
            });
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

    def test_the_price_calls_are_made_one_at_a_time(self):
        """WHY THAT MATTERS: the server keeps the last list it is told about,
        and the cart books from exactly that. Every change used to fire its
        own call, so an older one landing late replaced the kit with an
        earlier version of itself. Chained, the call the Add to Cart click
        waits for is the last one there is."""
        self._run_in_node("""
            const kit = page([HINGE, STRUT], [[1, 2]]);
            kit.templateId = 7;
            kit.total = { textContent: "", after: () => {} };
            kit.warn = () => {};
            const events = [];
            const bodies = [];
            let inFlight = 0;
            let unblock = null;
            sandbox.fetch = (url, options) => {
                bodies.push(JSON.parse(options.body).params.parts);
                inFlight += 1;
                events.push("start");
                assert.ok(inFlight <= 1, "two price calls in flight at once");

                return new Promise((resolve) => {
                    const answer = () => {
                        inFlight -= 1;
                        events.push("end");
                        resolve({ ok: true, json: async () => ({
                            result: { count: 2, total: 1, sent: 2 } }) });
                    };

                    if (!unblock) {
                        unblock = answer;      // hold the first one up
                    } else {
                        answer();
                    }
                });
            };

            const first = kit.price();
            kit.chosen.set(3, 5);          // the kit changes mid-flight
            const second = kit.price();
            // A tick, because the chain starts on a microtask: nothing has
            // gone out at the instant price() returns.
            await new Promise((resolve) => setTimeout(resolve, 0));
            assert.strictEqual(JSON.stringify(events), JSON.stringify(["start"]),
                "the second call went out while the first was still in flight");
            unblock();
            await Promise.all([first, second]);
            assert.strictEqual(
                JSON.stringify(events),
                JSON.stringify(["start", "end", "start", "end"]),
                "the calls overlapped, so an older list could land last");

            // AND THE LAST REQUEST CARRIES THE KIT AS IT IS NOW: the list is
            // read when a call goes out, not when it was queued, so the thing
            // the cart books from is never an older version of the kit.
            assert.strictEqual(
                JSON.stringify(bodies[bodies.length - 1]),
                JSON.stringify([{ variant_id: 1, quantity: 2 },
                                { variant_id: 3, quantity: 5 }]));
        """)

    def test_nothing_of_ours_sits_on_odoo_s_add_to_cart_click(self):
        """THE FAULT THIS FIXES, 2026-10-20. The production log for a whole day
        of trying: dozens of POST /aa/custom-kit/price and not one POST
        /shop/cart/add. The click went in and never came out.

        It was being caught here, held while the kit was sent, and let through
        on a second synthetic click - and Odoo 19 binds the #add_to_cart
        handler straight onto that node, where a re-dispatched click does not
        reliably reach it. The kit was never the problem. The button was.

        So the page no longer touches that click at all; it disables the
        button while a call is in flight instead, which is done to our own
        page rather than to Odoo's event.
        """
        from odoo.tools.misc import file_path

        with open(file_path(
                "aa_dealer_orders/static/src/js/custom_kit.js")) as handle:
            source = handle.read()

        for forbidden in ("stopImmediatePropagation", "aaCustomDone",
                          "button.click()"):
            self.assertNotIn(forbidden, source,
                             "the click is being interfered with again")

    def test_add_to_cart_is_locked_while_the_kit_is_in_mid_air(self):
        """The one gap left by not holding the click: a click in the instant
        between a change and its call landing. The button is disabled for
        exactly that long."""
        self._run_in_node("""
            const button = {
                classes: {}, attributes: {},
                classList: { toggle: (name, on) => { button.classes[name] = on; } },
                setAttribute: (name, value) => { button.attributes[name] = value; },
                removeAttribute: (name) => { delete button.attributes[name]; },
            };
            sandbox.document.querySelector = () => button;
            const kit = page([HINGE], [[1, 2]]);
            kit.templateId = 7;
            kit.total = { textContent: "", after: () => {} };
            kit.warn = () => {};
            let unblock;
            sandbox.fetch = () => new Promise((resolve) => {
                unblock = () => resolve({ ok: true, json: async () => ({
                    result: { count: 1, total: 2, sent: 1 } }) });
            });

            const sending = kit.price();
            await new Promise((resolve) => setTimeout(resolve, 0));
            assert.strictEqual(button.classes.disabled, true,
                "the kit can be added to a cart that has not been told about it");
            assert.strictEqual(button.attributes["aria-disabled"], "true");

            unblock();
            await sending;
            assert.strictEqual(button.classes.disabled, false,
                "the button was left disabled after the kit was saved");
            assert.strictEqual(button.attributes.title, undefined);
        """)

    def test_add_to_cart_stays_locked_when_the_kit_cannot_be_saved(self):
        """A kit the cart has not been told about must not be addable: it
        would book a box of nothing and look like a finished order."""
        self._run_in_node("""
            const button = {
                classes: {}, attributes: {},
                classList: { toggle: (name, on) => { button.classes[name] = on; } },
                setAttribute: (name, value) => { button.attributes[name] = value; },
                removeAttribute: (name) => { delete button.attributes[name]; },
            };
            sandbox.document.querySelector = () => button;
            const kit = page([HINGE], [[1, 2]]);
            kit.templateId = 7;
            kit.total = { textContent: "", after: () => {} };
            let said = "";
            kit.warn = (message) => { said = message; };
            sandbox.fetch = async () => { throw new Error("no network"); };

            await kit.price().then(
                () => { throw new Error("a failed save looked like a good one"); },
                () => {});
            assert.strictEqual(button.classes.disabled, true,
                "the button was unlocked after the kit failed to save");
            assert.ok(said.includes("could not be saved"), said);
        """)

    def test_the_colours_offered_are_the_ones_the_catalogue_sells(self):
        """Commonest first, and a part with no finish of its own is not a
        colour anybody can pick for the kit."""
        self._run_in_node("""
            const ONE_OFF = { name: "Almond latch", colours: [
                { id: 6, label: "White", finish: "White" },
                { id: 7, label: "Almond", finish: "Almond" }] };
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

    def test_a_part_that_is_not_in_stock_still_goes_in_the_kit(self):
        """THE FAULT THIS FIXES, 2026-10-20: the owner built a 13-part kit,
        the page priced it at $236.91, he added it to the cart - and got the
        kit on its own.

        website_sale_stock is installed, and it refuses a storable product
        that is not in stock: "... has not been added to your cart since it is
        not available", quantity clamped to zero, no line created. Every part
        of that kit is fitted to order rather than kept on a shelf, so every
        one of them was refused - and the warning core hands back was being
        dropped, so it happened in silence.

        A kit's contents are built to order, like the components of a
        phantom-BoM kit: nobody is stopped from ordering an AA 1200 because a
        hinge inside it shows zero on hand.
        """
        part = self.env["product.template"].create({
            "name": "Out Of Stock Strut", "type": "consu", "is_storable": True,
            "list_price": 6.0, "categ_id": self.category.id,
            "is_published": True, "aa_custom_kit_part": True,
            "allow_out_of_stock_order": False,
        })
        variant = part.product_variant_ids[:1]
        self.assertEqual(variant.qty_available, 0.0, "the fixture is stocked")

        self._build([{"variant_id": variant.id, "quantity": 6}])
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
        })
        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        booked = order.order_line.filtered(lambda line: line.product_id == variant)

        self.assertTrue(booked, "the part was thrown out for being out of stock")
        self.assertEqual(booked.product_uom_qty, 6.0)

    def test_the_shop_rule_is_scoped_and_not_removed(self):
        """OUT-OF-STOCK STILL MEANS OUT-OF-STOCK for anything a customer buys
        by itself. It is passed over only for lines a kit page books as the
        contents of a kit.

        Asserted at the method core asks rather than through the cart: an
        out-of-stock add is answered by clamping the quantity, and what then
        happens to the line is core's business and has moved between versions.
        What is ours is which answer that method gives.
        """
        part = self.env["product.template"].create({
            "name": "Out Of Stock Strut", "type": "consu", "is_storable": True,
            "list_price": 6.0, "categ_id": self.category.id,
            "is_published": True, "allow_out_of_stock_order": False,
        })
        variant = part.product_variant_ids[:1]
        order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.partner_admin").id})
        nothing = self.env["sale.order.line"]

        asked = 6.0
        allowed, warning = order._verify_updated_quantity(
            nothing, variant.id, asked, variant.uom_id.id)
        in_a_kit, kit_warning = order.with_context(
            aa_kit_parts=True)._verify_updated_quantity(
                nothing, variant.id, asked, variant.uom_id.id)

        self.assertLess(allowed, asked, "the shop sold what it has none of")
        self.assertTrue(warning)
        self.assertEqual(in_a_kit, asked, "the kit lost its part")
        self.assertFalse(kit_warning)

    def test_a_part_that_cannot_be_priced_does_not_lose_the_kit(self):
        """THE FAULT THIS FIXES, 2026-10-20: the owner started a kit from AA
        1200, watched it fill with that kit's parts, added it to the cart and
        got the kit plus ONE galvanised hinge at quantity one - not a quantity
        any parts list holds, but exactly what an earlier Add click had put on
        the page. The cart had been booked from an OLDER call.

        Because the kit used to be written to the session as the LAST thing
        the pricing route did, after a loop that reaches into pricelists,
        dealer rules and uoms for every part. One product that cannot be
        priced raised, the route ended before the kit was written down, the
        session kept what the previous call had left, and the cart was booked
        from that - silently, because a failed price only costs a figure on a
        page.

        So: pricing is made to fail here, and the kit must still reach the
        cart. What the customer chose is written down before any of it.
        """
        from unittest.mock import patch

        from odoo.addons.aa_dealer_orders.controllers import AAOptionPricing

        hinge = self._white_hinge()
        bracket = self.bracket.product_variant_ids[:1]

        def explode(self, partner, variant, no_variant, qty):
            raise ValueError("no price for %s" % variant.display_name)

        with patch.object(AAOptionPricing, "_unit_price", explode):
            priced = self._build([
                {"variant_id": hinge.id, "quantity": 4},
                {"variant_id": bracket.id, "quantity": 8},
            ])

        # The page is told about both parts, with no money against them.
        self.assertEqual(priced["count"], 2)
        self.assertEqual(priced["total"], 0.0)

        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
        })
        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        parts = order.order_line.filtered("linked_line_id")

        self.assertEqual(
            {(line.product_id, line.product_uom_qty) for line in parts},
            {(hinge, 4.0), (bracket, 8.0)},
            "the kit was lost because one part could not be priced")
        # AND IT IS PRICED PROPERLY IN THE CART, which is where the money is
        # actually worked out.
        self.assertGreater(sum(parts.mapped("price_subtotal")), 0.0)

    def test_the_page_is_told_how_many_parts_were_refused(self):
        """So a kit that reaches the cart short says so on the page first."""
        priced = self._build([
            {"variant_id": self._white_hinge().id, "quantity": 4},
            {"variant_id": self.secret.product_variant_ids[:1].id, "quantity": 1},
        ])

        self.assertEqual(priced["sent"], 2)
        self.assertEqual(priced["count"], 1, "the unticked part was taken")

    def test_the_parts_reach_the_cart_without_the_session(self):
        """WHY THE OTHER KITS WORK AND THIS ONE DID NOT (the owner's own
        question, 2026-10-20, and the right one).

        An ordinary AA kit's extras are ticked attributes posted IN the Add to
        Cart request, so the server reads them off what the browser just sent.
        A custom kit's parts were posted earlier, to the pricing route, and
        kept in the session - and on production that list was not there when
        the cart request ran. Measured rather than guessed: a cart add booking
        thirteen parts costs 271 queries, an empty one 89, and production's
        was 78, so the packing never even started.

        This books a kit WITHOUT ANY PRICING CALL FIRST - nothing in the
        session, nothing stored anywhere - and the parts must still arrive.
        """
        hinge = self._white_hinge()
        bracket = self.bracket.product_variant_ids[:1]

        added = self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
            "aa_custom_parts": json.dumps([
                {"variant_id": hinge.id, "quantity": 4},
                {"variant_id": bracket.id, "quantity": 8},
            ]),
        })
        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        parts = order.order_line.filtered("linked_line_id")

        self.assertEqual(
            {(line.product_id, line.product_uom_qty) for line in parts},
            {(hinge, 4.0), (bracket, 8.0)},
            "the kit arrived empty even though its parts were in the request")
        self.assertEqual(
            len((added.get("notification_info") or {}).get("lines") or []), 3)

    def test_a_parts_list_in_the_request_is_checked_like_any_other(self):
        """It comes from a browser either way, so it is checked against what is
        offered rather than against what was sent."""
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
            "aa_custom_parts": json.dumps([
                {"variant_id": self.secret.product_variant_ids[:1].id,
                 "quantity": 1},
                {"variant_id": self.cable.product_variant_ids[:1].id,
                 "quantity": 2},
            ]),
        })
        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)

        self.assertFalse(order.order_line.filtered("linked_line_id"),
                         "an unticked product and a cable were booked")

    def test_rubbish_in_the_request_falls_back_on_what_was_stored(self):
        """A parts list that is not JSON is not a reason to lose the kit."""
        hinge = self._white_hinge()
        self._build([{"variant_id": hinge.id, "quantity": 4}])
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
            "aa_custom_parts": "}{ not json",
        })
        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        parts = order.order_line.filtered("linked_line_id")

        self.assertEqual(parts.product_id, hinge)
        self.assertEqual(parts.product_uom_qty, 4.0)

    def test_the_page_sends_the_parts_with_the_cart_request(self):
        """The other half of it, in the page: the list is kept on the builder
        and added to Odoo's own cart request, which is how the working kits
        have always sent their ticks."""
        from odoo.tools.misc import file_path

        with open(file_path(
                "aa_dealer_orders/static/src/js/custom_kit_cart.js")) as handle:
            patched = handle.read()

        with open(file_path(
                "aa_dealer_orders/static/src/js/custom_kit.js")) as handle:
            builder = handle.read()

        # The patch lives in a file of its own: the builder is loaded as a
        # plain script by the tests above, which an import statement would
        # break.
        self.assertIn("_updateRootProduct", patched)
        self.assertIn("aa_custom_parts", patched)
        self.assertIn("dataset.aaParts", builder)

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

    def test_an_empty_kit_cannot_be_added_at_all(self):
        """Owner, 2026-10-28: *"you shouldnt be able to add the custom kit to
        the cart when there is nothing on it."*

        THIS TEST USED TO ASSERT THE OPPOSITE - that an empty kit still put
        its own line in the cart, with nothing hanging off it. That was never
        a decision, only what the code happened to do: the parts were added
        after the line and an empty list simply added none. A box of nothing,
        priced at nothing, which is exactly what he has now said no to.

        Refused in the CONTROLLER, before Odoo writes the line, so there is
        nothing to tidy up afterwards.
        """
        self._build([])
        before = self.env["sale.order"].search_count([])

        answer = self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_ids[:1].id,
            "quantity": 1,
        }, raw=True)

        self.assertIn("error", answer,
                      "an empty kit was accepted into the cart")
        self.assertIn(
            "at least one part",
            json.dumps(answer["error"]),
            "it was refused, but not for a reason anybody can act on")

        lines = self.env["sale.order.line"].search(
            [("product_id", "in", self.kit.product_variant_ids.ids)])

        self.assertFalse(lines, "a kit line was written and left behind")
        self.assertEqual(self.env["sale.order"].search_count([]), before)

    def test_a_silly_quantity_is_refused(self):
        hinge = self._white_hinge()
        priced = self._build([{"variant_id": hinge.id, "quantity": 100000}])

        self.assertEqual(priced["count"], 0, "an unbounded quantity got through")

    # --- and the page it is all shown on ---------------------------------------

    def test_the_page_says_which_build_it_is_running_to_staff_only(self):
        """WHY IT IS THERE, 2026-10-20: three faults in a row were reported
        against a build that did not have the code being discussed, because
        production carries whatever has been merged into it and nothing said
        what that was."""
        version = self.kit._aa_custom_kit_build()

        self.assertTrue(version, "an employee cannot tell which build this is")
        self.assertTrue(version.startswith("19.0."), version)

        public = self.env.ref("base.public_user")
        self.assertEqual(
            self.kit.with_user(public)._aa_custom_kit_build(), "",
            "a customer is being shown our build number")
        self.assertNotIn("Custom Kit build",
                         self.url_open(self.kit.website_url).text,
                         "the build number reached a public page")

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


@tagged("post_install", "-at_install")
class CustomKitZeroPriceCase(HttpCase):
    """A KIT THAT COSTS NOTHING UNTIL YOU PUT SOMETHING IN IT.

    Owner, 2026-10-27: *"there is a custom kit that should normally cost 0$
    until you start adding items, the problem is that the store doesnt detect
    that items have been added to the kit so it still believes the price is
    zero, and when you try to buy an item that costs 0$ it gives you a contact
    us button instead of an add to cart button."*

    The kit is priced at nothing ON PURPOSE - the parts carry the money, each
    on its own line (owner, 2026-10-20) - so the fix is not a price. It is
    Odoo's zero-price rule, which it enforces in five places that do not share
    a hook. Finding four and missing the fifth would be worse than finding
    none: the customer gets further each time and still cannot pay.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.website.prevent_zero_price_sale = True
        self.kit = self.env.ref("aa_dealer_orders.product_custom_kit")
        self.kit.write({"is_published": True, "list_price": 0.0})

    def _offers_contact_us(self, product):
        """Does this product's page show Contact Us instead of Add to Cart?

        READ OFF THE PAGE, not off `_get_combination_info` - which cannot be
        called under MockRequest at all, because the mocked pricelist comes
        back as a Mock and Odoo unpacks it. And the page is the thing he is
        looking at.

        Asked precisely: Odoo keeps BOTH blocks in the markup and hides one
        with `d-none`, and the words "Contact Us" are in the site menu of
        every page in the shop - which is why a plain `assertNotIn` for them
        failed on a page that was working.
        """
        page = self.url_open(product.website_url).text
        at = page.find('id="contact_us_wrapper"')

        self.assertNotEqual(at, -1, "the page has no contact-us block at all")

        return "d-none" not in page[at:at + 400]

    def test_the_page_offers_add_to_cart_and_not_contact_us(self):
        """THE ONE HE REPORTED."""
        self.assertFalse(self._offers_contact_us(self.kit),
                         "the kit page is still offering Contact Us")

    def test_an_ordinary_zero_priced_product_is_still_refused(self):
        """The setting is a good rule and the shop keeps it. Only the kit is
        excused, because only the kit's parts carry its money."""
        plain = self.env["product.template"].create({
            "name": "Somebody forgot to price this",
            "type": "consu", "is_published": True, "list_price": 0.0,
            "website_published": True})

        self.assertTrue(self._offers_contact_us(plain),
                        "an unpriced product became buyable for nothing")

    def test_the_server_lets_the_kit_into_a_cart(self):
        """Behind the button. A page that showed Add to Cart and a server
        that refused it would be the same bug one step later."""
        with MockRequest(self.env, website=self.website):
            self.assertTrue(
                self.kit.product_variant_id._is_add_to_cart_allowed())

    def test_the_line_is_not_refused_while_being_added(self):
        """`_check_validity` raises UserError on a line totalling nothing."""
        order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.public_partner").id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {
                "product_id": self.kit.product_variant_id.id,
                "product_uom_qty": 1, "price_unit": 0.0})],
        })

        order.order_line._check_validity()      # must not raise

    def test_a_full_cart_can_still_be_paid_for(self):
        """THE ONE THAT WOULD HAVE BEEN MISSED. `_get_zero_priced_lines` is
        not about adding to the cart at all - it blocks CHECKOUT, so without
        it the customer gets the kit and its parts in and is then refused at
        the payment step with nothing on screen to say why."""
        part = self.env["product.template"].create({
            "name": "A roller for the kit", "type": "consu",
            "is_published": True, "list_price": 9.0})
        order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.public_partner").id,
            "website_id": self.website.id,
            "order_line": [
                (0, 0, {"product_id": self.kit.product_variant_id.id,
                        "product_uom_qty": 1, "price_unit": 0.0}),
            ],
        })
        # HUNG OFF THE KIT, as the cart does it - that link is the whole
        # reason the kit line is excused its price.
        self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": part.product_variant_id.id,
            "product_uom_qty": 1, "price_unit": 9.0,
            "linked_line_id": order.order_line[0].id,
        })

        self.assertFalse(order._get_zero_priced_lines(),
                         "the cart could not have been paid for")

    def test_a_kit_left_empty_in_the_cart_cannot_be_paid_for(self):
        """Owner, 2026-10-28: "you shouldnt be able to add the custom kit to
        the cart when there is nothing on it."

        The controller refuses an empty one at the door, but a customer can
        also DELETE every part out of the cart afterwards and leave the kit
        sitting there. The excuse is that the money is on the lines hanging
        off it; with nothing hanging off it there is no excuse."""
        order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.public_partner").id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {
                "product_id": self.kit.product_variant_id.id,
                "product_uom_qty": 1, "price_unit": 0.0})],
        })

        self.assertTrue(order._get_zero_priced_lines(),
                        "an empty kit could have been paid for")

    def test_an_ordinary_zero_priced_line_still_blocks_checkout(self):
        plain = self.env["product.template"].create({
            "name": "Unpriced", "type": "consu", "is_published": True,
            "list_price": 0.0})
        order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.public_partner").id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {
                "product_id": plain.product_variant_id.id,
                "product_uom_qty": 1, "price_unit": 0.0})],
        })

        self.assertTrue(order._get_zero_priced_lines())

    def test_the_kit_page_shows_the_add_to_cart_button(self):
        """Over HTTP, because every assertion above is a model call and the
        thing he is looking at is a page. A route test caught exactly this
        class of miss on the pickup slots a day ago."""
        page = self.url_open(self.kit.website_url).text

        self.assertIn('id="aa_custom_kit"', page, "the builder is not there")
        self.assertIn("add_to_cart", page, "there is no Add to Cart button")
