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
        labels = [label for _, label in offered]
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
            sorted(label for _, label in bracket._aa_custom_kit_colours()),
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
        labels = sorted(label for _, label in anchor._aa_custom_kit_colours())

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
