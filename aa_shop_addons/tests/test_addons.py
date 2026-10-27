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

    def _labels(self, product):
        return [group["label"] for group in product._aa_addon_groups()]

    def _group(self, product, label):
        for group in product._aa_addon_groups():
            if group["label"] == label:
                return group
        return None

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

    def test_an_ordinary_product_gets_nothing(self):
        """A hinge is not a kit, and a row of add-ons under every product in
        the shop is noise."""
        self.assertFalse(self.cable._aa_addon_role())
        self.assertEqual(self.cable._aa_addon_groups(), [])

    # --- whose answer wins -------------------------------------------------

    def test_with_nothing_picked_it_falls_back_to_the_families(self):
        """A kit nobody has got to yet still shows the right KINDS, rather
        than an empty space under it."""
        self.assertEqual(self._labels(self.kit),
                         ["Cones", "Cables", "Tracks", "Trims"])

    def test_what_he_picked_beats_the_families(self):
        """THE WHOLE POINT. Asked how a kit should know its add-ons, the
        owner chose to set them himself - so a kit with a list shows that
        list and nothing else. Alternative Products, which is the one box he
        kept: "we only want the alternative products choice"."""
        self.kit.alternative_product_ids = [(6, 0, self.cable.ids)]

        self.assertEqual(self._labels(self.kit), ["Cables"])
        self.assertEqual(self._group(self.kit, "Cables")["products"],
                         self.cable)

    def test_his_pick_is_sorted_into_the_families_by_itself(self):
        """Setting one must not also mean saying which heading it
        belongs under - the product already says, by the category it is in."""
        self.kit.alternative_product_ids = [
            (6, 0, (self.cable | self.track).ids)]

        self.assertEqual(self._labels(self.kit), ["Cables", "Tracks"])

    def test_something_in_no_family_is_still_shown(self):
        """Otherwise the field would lie: he set a product and the page
        did not show it."""
        odd = self.env["product.template"].create({
            "name": "Weatherseal", "type": "consu", "is_published": True})
        self.kit.alternative_product_ids = [(6, 0, odd.ids)]

        self.assertEqual(self._labels(self.kit), ["Also needed"])
        self.assertEqual(self._group(self.kit, "Also needed")["products"], odd)

    def test_an_unpublished_pick_is_left_off(self):
        """It cannot be bought, so a card leading to nothing is worse than
        no card."""
        hidden = self._product("Not for sale", "Cables", published=False)
        self.kit.alternative_product_ids = [(6, 0, hidden.ids)]

        self.assertEqual(self._labels(self.kit), [])

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

        cones = self._group(spring, "Cones")

        self.assertTrue(cones, "the spring page showed no cones at all")
        self.assertIn("Already included", cones["note"])

    def test_a_kit_does_not_claim_its_cones_are_included(self):
        """A hardware kit has no spring in it and no cones with it, so the
        warning would be a lie."""
        self.assertEqual(self._group(self.kit, "Cones")["note"], "")

    # --- the fallback can be pointed somewhere else ------------------------

    def test_a_category_called_something_else_can_be_set(self):
        """His cables live under "Lift Cables" rather than "Cables" on some
        catalogues, and that must not need a deploy to fix."""
        self.categories["Cables"].name = "Lift Cables"

        self.assertNotIn("Cables", self._labels(self.kit))

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_shop_addons.category_cables", self.categories["Cables"].id)

        self.assertIn("Cables", self._labels(self.kit))


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
