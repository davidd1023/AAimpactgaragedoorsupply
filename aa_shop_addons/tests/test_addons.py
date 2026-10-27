"""THE ADD-ONS UNDER A KIT OR A SPRING.

Owner, 2026-10-27: "Done when: each kit shows its correct add-ons." Correct
is his to decide, so the tests that matter are the ones about WHOSE answer
wins - the list he picked over the family fallback - and the one about the
cones note, which exists so a customer does not buy a second set of cones
they are already paying for.
"""

from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class ShopAddonsCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.categories = {}

        for name in ("Cones", "Cables", "Tracks", "Trims"):
            self.categories[name] = self.env["product.public.category"].create(
                {"name": name})

        self.cable = self._product("Lift Cable 5/32\" Pair", "Cables")
        self.track = self._product("2\" Horizontal Track", "Tracks")
        self.trim = self._product("Trims", "Trims")
        self.cone = self._product("Cone Set 3 3/4\"", "Cones")

        self.kit = self.env["product.template"].create({
            "name": "1200 Series Hardware Kit - 4 Panel",
            "default_code": "HK-1200-4P",
            "type": "consu", "list_price": 180.0, "is_published": True,
        })

    def _product(self, name, category, published=True):
        return self.env["product.template"].create({
            "name": name,
            "type": "consu",
            "list_price": 20.0,
            "is_published": published,
            "public_categ_ids": [(6, 0, [self.categories[category].id])],
        })

    def _shown(self, product):
        """The one pool the page will draw (owner, 2026-10-27: "just one pool
        of products not multiple categories")."""
        return product._aa_addon_picks().get(
            "products", self.env["product.template"])

    def _note(self, product):
        return product._aa_addon_picks().get("note", "")

    # --- which products get a block at all ---------------------------------

    def test_a_kit_is_known_by_its_part_number(self):
        self.assertEqual(self.kit._aa_addon_role(), "kit")

    def test_a_kit_is_known_by_its_category_too(self):
        """A kit added by hand later may well not follow the SKU."""
        parent = self.env["product.category"].create({"name": "Hardware Kits"})
        odd = self.env["product.template"].create({
            "name": "A kit somebody typed in", "categ_id": parent.id,
            "type": "consu", "is_published": True,
        })

        self.assertEqual(odd._aa_addon_role(), "kit")

    def test_the_custom_spring_is_known(self):
        spring = self.env.ref("spring_engineering.product_custom_spring",
                              raise_if_not_found=False)

        if not spring:
            self.skipTest("spring_engineering is not installed here")

        self.assertEqual(spring._aa_addon_role(), "spring")

    # --- HIS OWN KITS, which are not the ones this was written against ----
    #
    # Owner, 2026-10-27: "i dont see the recommended products under the kits,
    # and yes i did put the categories in the garage door add-ons in the
    # settings." Answering it meant crawling the live site, where the kits
    # turned out to be AA-1200, AA-1600, AA-1800 and AA-Custom, in the WEBSITE
    # category "Hardware Kits", with no HK- part number anywhere. The feature
    # had never drawn a thing, because nothing was read as a kit at all.

    def _his_kit(self):
        kits = self.env["product.public.category"].create(
            {"name": "Hardware Kits"})

        return self.env["product.template"].create({
            "name": "AA-1200 Hardware Kit",
            "type": "consu", "list_price": 180.0, "is_published": True,
            "public_categ_ids": [(6, 0, kits.ids)],
        }), kits

    def test_his_own_kit_is_read_as_a_kit(self):
        """THE ONE THAT SETTLES IT. No HK- code, no product category saying
        kit - just the website category and the name, which are what his
        catalogue actually has."""
        kit, _categ = self._his_kit()

        self.assertEqual(kit._aa_addon_role(), "kit")
        self.assertTrue(self._shown(kit),
                        "his own kit still draws nothing under it")

    def test_a_kit_named_one_is_a_kit_even_with_no_category(self):
        """A product that says "Hardware Kit" in its name is a hardware kit.
        Refusing to read the name and demanding a part number was the
        mistake."""
        bare = self.env["product.template"].create({
            "name": "AA-Custom Custom Kit - Hardware Kit", "type": "consu",
            "is_published": True})

        self.assertEqual(bare._aa_addon_role(), "kit")

    def test_the_kits_category_can_be_pointed_at(self):
        """For a catalogue that calls them something sharing no word with
        "hardware kit" at all."""
        odd = self.env["product.public.category"].create({"name": "Bundles"})
        kit = self.env["product.template"].create({
            "name": "AA-1600", "type": "consu", "is_published": True,
            "public_categ_ids": [(6, 0, odd.ids)]})

        self.assertFalse(kit._aa_addon_role())

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.category_kits", odd.id)

        self.assertEqual(kit._aa_addon_role(), "kit")

    def test_a_family_category_need_not_be_named_exactly(self):
        """HIS SITE HAS NO "Cables" CATEGORY. It has none called Cones or
        Trims either - only Tracks matched, one of four - so an exact name
        match found almost nothing. "Cables" now finds "Lift Cables"."""
        self.categories["Cables"].name = "Lift Cables"

        self.assertIn(self.cable, self._shown(self.kit))

    def test_a_singular_category_is_found_too(self):
        """"Trims" dropped to "trim" finds "Trim Molding"."""
        self.categories["Trims"].name = "Trim Molding"

        self.assertIn(self.trim, self._shown(self.kit))

    def test_the_check_screen_says_what_a_page_will_draw(self):
        """Answering "i dont see them" by crawling his website is not a way to
        answer the same question twice."""
        kit, _categ = self._his_kit()
        plain = self.env["product.template"].create({
            "name": "A hinge", "type": "consu", "is_published": True})

        self.assertIn("not read as a kit", plain.aa_addon_summary)
        self.assertIn("products", kit.aa_addon_summary)
        self.assertIn("a spread of the families", kit.aa_addon_summary)

    def test_the_check_screen_lists_the_kits(self):
        kit, _categ = self._his_kit()
        action = self.env["product.template"].action_aa_addon_check()
        listed = self.env["product.template"].search(action["domain"])

        self.assertIn(kit, listed)
        self.assertIn(self.kit, listed)
        self.assertNotIn(self.cable, listed)

    def test_an_ordinary_product_gets_nothing(self):
        """A hinge is not a kit, and a row of add-ons under every product in
        the shop is noise."""
        self.assertFalse(self.cable._aa_addon_role())
        self.assertEqual(self.cable._aa_addon_picks(), {})

    # --- whose answer wins -------------------------------------------------

    def test_with_nothing_picked_it_falls_back_to_the_families(self):
        """A kit nobody has got to yet still shows the right KINDS, rather
        than an empty space under it - ONE POOL, taken in turns round the
        families so it is a spread and not eight cones."""
        shown = self._shown(self.kit)

        for product in (self.cone, self.cable, self.track, self.trim):
            self.assertIn(product, shown,
                          "%s was pushed off the end of the pool" % product.name)

    def test_the_pool_is_capped_so_a_page_is_not_a_catalogue(self):
        """Owner, 2026-10-27: "that way we dont show too many products in the
        recommendations." It was four headings with up to eight under each."""
        for n in range(12):
            self._product("Lift Cable %d" % n, "Cables")

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.shown", "4")

        self.assertEqual(len(self._shown(self.kit)), 4)

    def test_how_many_to_show_can_be_moved_without_a_deploy(self):
        """"Too many" is his judgement, not a number for the code."""
        self.assertEqual(self.env["product.template"]._aa_addon_shown(), 8)

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.shown", "3")

        self.assertEqual(self.env["product.template"]._aa_addon_shown(), 3)

    def test_what_he_picked_beats_the_families(self):
        """THE WHOLE POINT. Asked how a kit should know its add-ons, the
        owner chose to set them himself - so a kit with a list shows that
        list and nothing else. Alternative Products, which is the one box he
        kept: "we only want the alternative products choice"."""
        self.kit.alternative_product_ids = [(6, 0, self.cable.ids)]

        self.assertEqual(self._shown(self.kit), self.cable)

    def test_his_pick_is_shown_whole_and_in_one_row(self):
        """No headings to sort it into any more - what he set is what shows."""
        self.kit.alternative_product_ids = [
            (6, 0, (self.cable | self.track).ids)]

        self.assertEqual(self._shown(self.kit), self.cable | self.track)

    def test_something_in_no_family_is_still_shown(self):
        """Otherwise the field would lie: he set a product and the page
        did not show it."""
        odd = self.env["product.template"].create({
            "name": "Weatherseal", "type": "consu", "is_published": True})
        self.kit.alternative_product_ids = [(6, 0, odd.ids)]

        self.assertEqual(self._shown(self.kit), odd)

    def test_an_unpublished_pick_is_left_off(self):
        """It cannot be bought, so a card leading to nothing is worse than
        no card."""
        hidden = self._product("Not for sale", "Cables", published=False)
        self.kit.alternative_product_ids = [(6, 0, hidden.ids)]

        self.assertEqual(self._shown(self.kit),
                         self.env["product.template"])

    # --- the cones note ----------------------------------------------------

    def test_the_spring_warns_that_cones_are_already_included(self):
        """Owner, 2026-10-27: "show them but make it obvious that the cones
        are included so customers dont make the mistake of buying when they
        dont need one." His calculator prices the cone set into the spring,
        so a row of cones underneath reads as something missing."""
        spring = self.env.ref("spring_engineering.product_custom_spring",
                              raise_if_not_found=False)

        if not spring:
            self.skipTest("spring_engineering is not installed here")

        self.assertIn(self.cone, self._shown(spring),
                      "the spring page showed no cones at all")
        self.assertIn("Already included", self._note(spring))

    def test_a_kit_does_not_claim_its_cones_are_included(self):
        """A hardware kit has no spring in it and no cones with it, so the
        warning would be a lie."""
        self.assertIn(self.cone, self._shown(self.kit))
        self.assertEqual(self._note(self.kit), "")

    # --- the fallback can be pointed somewhere else ------------------------

    def test_a_category_sharing_no_word_can_still_be_set(self):
        """"Lift Cables" is found by itself now - see
        test_a_family_category_need_not_be_named_exactly. The setting is for
        the case the word check cannot reach, and it must not need a deploy."""
        self.categories["Cables"].name = "Flexible Steel Rope"

        self.assertNotIn(self.cable, self._shown(self.kit))

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.category_cables", self.categories["Cables"].id)

        self.assertIn(self.cable, self._shown(self.kit))


@tagged("post_install", "-at_install")
class LearnedAddonsCase(ShopAddonsCase):
    """RECOMMENDED FROM HIS OWN ORDERS, so nobody has to type them in.

    Owner, 2026-10-27: *"could you automate a system that will recommend
    additional products the same way that the alternative product thing works.
    this way i wont have to individually go into every products page to seach
    which products i should recommend alongside it."*

    The thing being tested is a count, so the tests are about what must NOT be
    counted: a quotation nobody accepted, an order somebody cancelled, two
    lines of the same product, and one order on its own - each of which would
    put a product on the website on the strength of nothing.
    """

    def setUp(self):
        super().setUp()
        self.customer = self.env["res.partner"].create({"name": "A fitter"})
        self.suggestions = self.env["aa.addon.suggestion"]

    # --- fixtures ---------------------------------------------------------

    def _order(self, products, state="sale"):
        """One order carrying each of these templates. `products` may repeat a
        template, which is how "one order is one vote" is tested."""
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {
                "product_id": template.product_variant_id.id,
                "product_uom_qty": 1,
            }) for template in products],
        })
        order.write({"state": state})

        return order

    def _rebuild(self):
        self.suggestions._aa_rebuild()

        return self.suggestions.search([
            ("product_tmpl_id", "=", self.kit.id)])

    def _recommended(self):
        return self.suggestions._aa_for(self.kit)

    # --- the sentence he wrote --------------------------------------------

    def test_two_orders_put_a_cable_under_the_kit_with_nobody_typing_it(self):
        """THE ONE THAT SETTLES IT. Nothing is set on the kit; the cable
        appears under it because his own shop has sold the two together."""
        self._order([self.kit, self.cable])
        self._order([self.kit, self.cable])

        rows = self._rebuild()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.addon_tmpl_id, self.cable)
        self.assertEqual(rows.orders, 2)
        self.assertEqual(self._shown(self.kit), self.cable)

    def test_the_count_beats_the_families(self):
        """The point of counting. Before, a kit nobody had got to showed every
        cable in the catalogue under Cables; now it shows the one that sells
        with it."""
        other = self._product("Lift Cable 1/8\" Pair", "Cables")
        self._order([self.kit, self.cable])
        self._order([self.kit, self.cable])
        self._rebuild()

        shown = self._shown(self.kit)

        self.assertEqual(shown, self.cable)
        self.assertNotIn(other, shown, "the family fallback is still running")

    def test_the_commonest_comes_first(self):
        """"Which cable do people who buy this kit buy" has an order to its
        answer, and a many2many would have thrown it away."""
        rare = self._product("Lift Cable 1/8\" Pair", "Cables")

        for _ in range(3):
            self._order([self.kit, self.cable])
        for _ in range(2):
            self._order([self.kit, rare])

        self._rebuild()

        self.assertEqual(list(self._recommended())[:2], [self.cable, rare])

    def test_his_own_pick_still_wins_outright(self):
        """He decided on 2026-10-27 that his list is right by definition.
        Counting orders is a convenience, not an overruling."""
        self._order([self.kit, self.cable])
        self._order([self.kit, self.cable])
        self._rebuild()
        self.kit.alternative_product_ids = [(6, 0, self.track.ids)]

        self.assertEqual(self._shown(self.kit), self.track)

    def test_a_roller_he_would_never_have_gone_looking_for(self):
        """His four families were an answer about cones, cables, tracks and
        trims. His order book knows about rollers too, and those are exactly
        the ones nobody would have thought to put on the page."""
        roller = self.env["product.template"].create({
            "name": "Nylon Roller 7\" Stem", "type": "consu",
            "list_price": 4.5, "is_published": True})
        self._order([self.kit, roller])
        self._order([self.kit, roller])
        self._rebuild()

        self.assertEqual(self._shown(self.kit), roller,
                         "a roller fits none of the four families and would"
                         " have been dropped when there were headings")

    # --- what must not be counted -----------------------------------------

    def test_one_order_is_an_anecdote(self):
        """Two by default, because one customer buying two things together is
        not a habit - and a page full of coincidences is worse than a page of
        families."""
        self._order([self.kit, self.cable])

        self.assertFalse(self._rebuild())
        self.assertIn(self.cone, self._shown(self.kit),
                      "it did not fall back to the families")

    def test_a_quotation_nobody_accepted_does_not_count(self):
        """Somebody thinking out loud at a keyboard is not a sale."""
        self._order([self.kit, self.cable], state="draft")
        self._order([self.kit, self.cable], state="sent")

        self.assertFalse(self._rebuild())

    def test_a_cancelled_order_does_not_count(self):
        """A customer who changed their mind is evidence of nothing."""
        self._order([self.kit, self.cable], state="cancel")
        self._order([self.kit, self.cable], state="cancel")

        self.assertFalse(self._rebuild())

    def test_one_order_is_one_vote(self):
        """Two lengths of the same track on one order is one customer buying
        track, not two - and since the catalogue merge a track IS one product
        with twenty combinations behind it, so this is the common case."""
        self._order([self.kit, self.track, self.track])

        self.assertFalse(
            self._rebuild(),
            "one order counted twice because it had two lines of the track")

    def test_an_unpublished_product_is_never_recommended(self):
        """It cannot be reached, so a card leading nowhere is worse than no
        card. The plastic filler is unpublished on purpose and is excluded by
        this same rule, which is the point of having it."""
        hidden = self._product("Not for sale", "Cables", published=False)
        self._order([self.kit, hidden])
        self._order([self.kit, hidden])

        self.assertFalse(self._rebuild())

    def test_a_delivery_charge_is_not_an_add_on(self):
        """It is on more orders than anything else in the shop and belongs
        under nothing."""
        carriage = self.env["product.template"].create({
            "name": "Delivery", "type": "service", "list_price": 15.0,
            "is_published": True})
        self._order([self.kit, carriage])
        self._order([self.kit, carriage])

        self.assertFalse(self._rebuild())

    def test_only_kits_and_the_spring_are_counted_for(self):
        """There is no point counting pairs for fifteen hundred products when
        nothing would ever read them."""
        self._order([self.cable, self.track])
        self._order([self.cable, self.track])
        self.suggestions._aa_rebuild()

        self.assertFalse(
            self.suggestions.search([("product_tmpl_id", "=", self.cable.id)]))

    # --- keeping it true --------------------------------------------------

    def test_rebuilding_replaces_rather_than_tops_up(self):
        """A pair that has stopped selling together should stop being
        recommended. A table that only grows recommends last spring's track
        for ever."""
        orders = [self._order([self.kit, self.cable]) for _ in range(2)]

        self.assertTrue(self._rebuild())

        orders[0].write({"state": "cancel"})

        self.assertFalse(self._rebuild())

    def test_the_threshold_can_be_moved_without_a_deploy(self):
        """How many orders make a habit depends on how much history there is,
        which is not a number to need a deploy for."""
        self._order([self.kit, self.cable])

        self.assertFalse(self._rebuild())

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.min_orders", "1")

        self.assertTrue(self._rebuild())

    def test_an_unset_threshold_is_two_and_not_nothing(self):
        """An unset parameter reads as False and `int(False)` is a perfectly
        good 0, which clamped to 1 and made every coincidence a
        recommendation. The first deploy said so in its own log line."""
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "aa_shop_addons.min_orders")]).unlink()

        self.assertEqual(self.suggestions._aa_min_orders(), 2)

    def test_nonsense_in_the_setting_falls_back_rather_than_failing(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.min_orders", "every other Tuesday")

        self.assertEqual(self.suggestions._aa_min_orders(), 2)


@tagged("post_install", "-at_install")
class ShopAddonsPageCase(HttpCase):
    """THE BLOCK HAS TO RENDER, not just compute.

    Everything above tests the Python. A mistake in the QWeb - a field that
    does not exist on this version, a currency that is not in the context -
    shows up nowhere until somebody opens the page and gets a 500. So the
    page is actually fetched.
    """

    def test_a_kit_page_renders_with_its_add_ons(self):
        category = self.env["product.public.category"].create({"name": "Cables"})
        self.env["product.template"].create({
            "name": "Lift Cable 5/32\" Pair",
            "type": "consu", "list_price": 21.5, "is_published": True,
            "public_categ_ids": [(6, 0, category.ids)],
        })
        kit = self.env["product.template"].create({
            "name": "1200 Series Hardware Kit - 4 Panel",
            "default_code": "HK-1200-4P",
            "type": "consu", "list_price": 180.0, "is_published": True,
        })
        self.env["website"].search([], limit=1).ensure_one()

        page = self.url_open(kit.website_url)

        self.assertEqual(page.status_code, 200, "the kit page did not render")
        self.assertIn("aa_shop_addons", page.text,
                      "the add-ons block is not on the page")
        self.assertIn("Lift Cable", page.text,
                      "the block rendered but listed nothing")

    def test_an_ordinary_product_page_has_no_block(self):
        plain = self.env["product.template"].create({
            "name": "A hinge", "type": "consu", "list_price": 2.4,
            "is_published": True,
        })

        page = self.url_open(plain.website_url)

        self.assertEqual(page.status_code, 200)
        self.assertNotIn("aa_shop_addons", page.text)
