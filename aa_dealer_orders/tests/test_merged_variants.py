"""THE DEALER PAGES, ONCE A PART IS ONE PRODUCT WITH CHOICES ON IT.

The catalogue's colours, sizes and hands were folded into one product per part
(owner, 2026-10-21; spring_engineering/models/variant_families). Two things on
this side read a catalogue that no longer looks the way they were written for:

  * the custom kit picker, which offered a colour dropdown per part - and a
    part that now has a size as well as a colour needs both in the label, or
    it offers "Black" seven times and hands over whichever size comes first;
  * the trims lookup, which found three products by name - "White Trims",
    "Bronze Trims", "Black Trims" - and now has to find one product's three
    colours instead, without losing the ability to read the old shape, since
    the owner's database is the old shape until the migration runs.
"""

from odoo.tests import TransactionCase, tagged

from ..door_options import Catalog


@tagged("post_install", "-at_install")
class TestDealerPagesAfterTheMerge(TransactionCase):

    def _product(self, name, code=None, price=1.0, published=True):
        return self.env["product.template"].create({
            "name": name,
            "default_code": code,
            "type": "consu",
            "is_storable": True,
            "list_price": price,
            "sale_ok": True,
            "is_published": published,
        })

    def _merge(self, survivor):
        reports = self.env["product.template"]._aa_merge_variant_families(
            dry_run=False, only=[survivor])
        self.assertEqual(reports[0]["state"], "merged", reports[0])
        return self.env["product.template"].search(
            [("name", "=", survivor)], limit=1)

    # --- the custom kit picker -------------------------------------------

    def test_a_hinge_dropdown_names_the_size_as_well_as_the_colour(self):
        """Nine sizes and three colours - minus the two he has never stocked -
        is 25 variants on one product. The dealer has to be able to tell them
        apart."""
        # Nine sizes, and Galvanized only to #7 - his catalogue, not a tidy
        # version of it. 25 products, so 25 rows in the dropdown.
        for n in range(1, 10):
            for colour in (("Black", "White", "Galvanized") if n <= 7
                           else ("Black", "White")):
                self._product("Hinge # %d %s" % (n, colour),
                              code="CH1411-%d" % n, price=2.4 + n * 0.1)

        hinge = self._merge("Hinge")
        offered = hinge._aa_custom_kit_colours()

        self.assertEqual(len(offered), 25)
        labels = [label for _, label, _finish in offered]
        self.assertEqual(
            len(set(labels)), 25,
            "the dealer is offered the same label more than once: %s"
            % sorted(labels))
        self.assertIn("#3 Black", labels)
        self.assertIn("#7 Galvanized", labels)

    def test_a_part_that_only_comes_in_colours_reads_as_it_always_did(self):
        """The fix must not change the ordinary case: a top bracket in two
        colours is still just "Black" and "White"."""
        for colour in ("Black", "White"):
            self._product("Top Bracket %s" % colour, code="CH1103", price=2.61)

        bracket = self._merge("Top Bracket")

        self.assertEqual(
            sorted(label for _, label, _f in bracket._aa_custom_kit_colours()),
            ["Black", "White"],
        )

    def test_a_bracket_with_a_hand_says_which_hand(self):
        """The one part in the catalogue that has an LH and an RH. Wrong
        colour is an annoyance; wrong hand will not mount."""
        for hand in ("LH", "RH"):
            for colour in ("Black", "White"):
                self._product("Spring Anchor Bracket %s %s" % (hand, colour),
                              code="CH1119D", price=6.91)

        anchor = self._merge("Spring Anchor Bracket")
        labels = sorted(
            label for _, label, _f in anchor._aa_custom_kit_colours())

        self.assertEqual(labels, ["LH Black", "LH White", "RH Black", "RH White"])

    # --- the trims lookup -------------------------------------------------

    def _trim_products(self):
        return {colour: self._product("%s Trims" % colour,
                                      code="R2-%s18" % colour[:2].upper(),
                                      price=33.16)
                for colour in ("White", "Bronze", "Black")}

    def test_the_trims_are_found_the_old_way(self):
        """Proved on today's shape first, so a failure after the merge is the
        merge's fault and not a test that never worked."""
        made = self._trim_products()

        catalog = Catalog(self.env)

        for colour, tmpl in made.items():
            self.assertEqual(catalog.trims.get(colour),
                             tmpl.product_variant_id, colour)

    def test_the_trims_are_still_found_once_they_are_one_product(self):
        """Without this the dealer's kit comes back with "no White trims
        product found - AA will add them" on every order."""
        self._trim_products()

        self._merge("Trims")
        catalog = Catalog(self.env)

        for colour in ("White", "Bronze", "Black"):
            found = catalog.trims.get(colour)
            self.assertTrue(found, "%s trims were lost in the merge" % colour)
            self.assertEqual(found._aa_chosen_colour(), colour)
        # Three colours, three different variants - not the same one thrice.
        self.assertEqual(len({p.id for p in catalog.trims.values()}), 3)

    # --- the kit's own colour box, which is not the per-part dropdown -----

    def test_the_kit_colour_box_offers_finishes_not_every_variant(self):
        """Owner, 2026-10-22: "the custom kits color option next to the start
        from kit options is showing a lot of options when it should only show
        3, white black or galvanized."

        It was built from the per-part LABELS, which name the whole variant -
        "#3 Black" - because a hinge is now one product with 25 of them. The
        box wants the FINISH alone, which is three."""
        for n in range(1, 10):
            for colour in (("Black", "White", "Galvanized") if n <= 7
                           else ("Black", "White")):
                self._product("Hinge # %d %s" % (n, colour),
                              code="CH1411-%d" % n, price=2.4 + n * 0.1)
        hinge = self._merge("Hinge")

        offered = hinge._aa_custom_kit_colours()
        finishes = {finish for _id, _label, finish in offered}
        labels = {label for _id, label, _finish in offered}

        self.assertEqual(finishes, {"Black", "White", "Galvanized"})
        self.assertEqual(len(labels), 25, "the per-part dropdown still names"
                                          " every variant")

    def test_a_part_with_no_finish_offers_no_finish(self):
        """A product whose colour is in its name has one variant and nothing
        to put in the kit's colour box - the kit colour must not move it."""
        shaft = self._product("Torsion Solid Shaft 9'6\"", code="CH-SH02")

        offered = shaft._aa_custom_kit_colours()

        self.assertEqual(len(offered), 1)
        self.assertEqual(offered[0][2], "", "it offered a finish it has not got")

    # --- the dealer's track catalogue, on both sides of the merge ---------

    def _track(self, name, code=None):
        return self._product(name, code=code, price=120.0)

    def test_the_dealer_catalogue_finds_todays_tracks(self):
        """Proved on today's shape first, so a failure afterwards is the
        merge's fault and not a test that never worked."""
        self._track('2" Horizontal Track -  120" White', code='CH-HT-2"')
        self._track('3" Vertical Track 76" - 7\' Door Height Black',
                    code='CH-VT-3"')

        catalog = Catalog(self.env)

        self.assertIn(("2", 120, "White"),
                      [row[:3] for row in catalog.horizontal])
        self.assertIn(("3", 76, "Black"),
                      [row[:3] for row in catalog.vertical])

    def test_the_dealer_catalogue_finds_folded_tracks(self):
        """One product per size and type, with the length and finish as
        variant values. Without this the Quick Order answers "no prepared
        track" for every door."""
        template = self.env["product.template"].create({
            "name": '2" Horizontal Track', "default_code": 'CH-HT-2"',
            "type": "consu", "is_storable": True, "list_price": 122.75,
            "sale_ok": True})
        for ref, values in (
            ("spring_engineering.attribute_finish_colour", ["Black", "White"]),
            ("spring_engineering.attribute_track_length", ['96"', '120"']),
        ):
            attribute = self.env.ref(ref)
            options = self.env["product.attribute.value"]
            for name in values:
                options |= self.env["product.attribute.value"].search([
                    ("attribute_id", "=", attribute.id), ("name", "=", name)
                ], limit=1) or self.env["product.attribute.value"].create({
                    "attribute_id": attribute.id, "name": name})
            self.env["product.template.attribute.line"].create({
                "product_tmpl_id": template.id, "attribute_id": attribute.id,
                "value_ids": [(6, 0, options.ids)]})
        template.invalidate_recordset()

        catalog = Catalog(self.env)
        found = [row[:3] for row in catalog.horizontal]

        self.assertEqual(len(template.product_variant_ids), 4)
        for want in (("2", 96, "Black"), ("2", 96, "White"),
                     ("2", 120, "Black"), ("2", 120, "White")):
            self.assertIn(want, found, found)

    def test_raw_track_stock_never_enters_the_catalogue(self):
        """RAW is what a track is cut from, and the owner kept it out of the
        merge. Offering one to a dealer would sell uncut stock as a door's
        track."""
        self._track('3" Horizontal Track RAW - 9\'6" Galvanized')

        catalog = Catalog(self.env)

        self.assertFalse(catalog.horizontal, catalog.horizontal)
