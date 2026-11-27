"""THE RAW TRACKS FOLDED INTO VARIANTS (owner, 2026-11-27).

"crea variantes con todos los tracks raws de todas sus medidas al igual que
los terminados de 2" y 3"" - with ATL kept as a choice on the same product
and every piece keeping its own AA Part #.

What has to survive: the stock on the right length, finish and line; the part
numbers; the 2x2 angle an ATL piece needs bolted on, which lived on the ATL
TEMPLATE and has to come down to the variant; the CHI/ATL pairing, which was
template to template and is now variant to variant; and every RAW reader on
the shop floor, which used to read the length out of the name.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRawTrackMerge(TransactionCase):

    SURVIVOR = '3" Horizontal Track RAW'

    def setUp(self):
        super().setUp()
        self.stock = self.env.ref("stock.stock_location_stock")

    def _product(self, name, stock=0.0, cost=10.0):
        tmpl = self.env["product.template"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "list_price": 1.0,
            "standard_price": cost,
            "purchase_ok": True,
            "sale_ok": False,
        })
        if stock:
            quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
                "product_id": tmpl.product_variant_id.id,
                "location_id": self.stock.id,
                "inventory_quantity": stock,
            })
            quant.action_apply_inventory()
        return tmpl

    def _family(self):
        """His 3" horizontals as they are named: Black and White in three
        lengths, Galvanized in four, and the ATL Galvanized in two."""
        made = {}
        for length, qty in (("9'6\"", 10.0), ("11'6\"", 20.0), ("15'6\"", 4.0)):
            for colour in ("Black", "White"):
                name = '3" Horizontal Track RAW - %s %s' % (length, colour)
                made[name] = self._product(name, stock=qty if colour == "Black" else 2.0,
                                           cost=50.0 + qty)
        for length in ("9'6\"", "10'6\"", "11'6\"", "17'6\""):
            name = '3" Horizontal Track RAW - %s Galvanized' % length
            made[name] = self._product(name, stock=3.0)
        for length in ("10'6\"", "11'6\""):
            name = '3" Horizontal Track RAW - %s Galvanized ATL' % length
            made[name] = self._product(name, stock=5.0, cost=133.0)
        return made

    def _merge(self, dry_run=False):
        reports = self.env["product.template"]._aa_merge_variant_families(
            dry_run=dry_run, only=[self.SURVIVOR])
        self.assertEqual(len(reports), 1, reports)
        return reports[0]

    def _variant(self, **combo):
        survivor = self.env["product.template"].search([("name", "=", self.SURVIVOR)])
        for variant in survivor.product_variant_ids:
            got = {v.attribute_id.name: v.name
                   for v in variant.product_template_attribute_value_ids}
            if got == combo:
                return variant
        return self.env["product.product"]

    # --- reading a RAW track, both shapes --------------------------------

    def test_the_reader_reads_the_old_names(self):
        made = self._family()
        facts = made['3" Horizontal Track RAW - 9\'6" Black'] \
            .product_variant_id._aa_raw_track_facts()
        self.assertEqual(facts, {"kind": "horizontal", "size": "3", "inches": 114,
                                 "colour": "Black", "line": "chi"})
        atl = made['3" Horizontal Track RAW - 10\'6" Galvanized ATL'] \
            .product_variant_id._aa_raw_track_facts()
        self.assertEqual((atl["inches"], atl["colour"], atl["line"]),
                         (126, "Galvanized", "atl"))

    def test_a_prepared_track_is_not_a_raw_track_and_back(self):
        prepared = self._product('3" Horizontal Track - 108" Black')
        raw = self._product('3" Horizontal Track RAW - 9\'6" Black')
        self.assertIsNone(prepared.product_variant_id._aa_raw_track_facts())
        self.assertIsNone(raw.product_variant_id._aa_track_facts())

    # --- the merge --------------------------------------------------------

    def test_one_product_with_length_colour_and_line(self):
        self._family()
        report = self._merge()
        self.assertEqual(report["state"], "merged", report)
        # 12 old products; the combinations never stocked are archived.
        self.assertEqual(report["variants"], 12, report)
        survivor = self.env["product.template"].search([("name", "=", self.SURVIVOR)])
        self.assertEqual(len(survivor.product_variant_ids), 12)
        self.assertFalse(self._variant(**{"Stock Length": "9'6\"", "Colour": "Black",
                                          "Line": "ATL"}))

    def test_the_stock_lands_on_the_right_piece(self):
        self._family()
        self._merge()
        black = self._variant(**{"Stock Length": "11'6\"", "Colour": "Black", "Line": "CHI"})
        atl = self._variant(**{"Stock Length": "10'6\"", "Colour": "Galvanized", "Line": "ATL"})
        self.assertEqual(black.qty_available, 20.0)
        self.assertEqual(atl.qty_available, 5.0)
        self.assertEqual(atl.standard_price, 133.0)

    def test_the_merged_variants_still_read_as_raw_track(self):
        self._family()
        self._merge()
        atl = self._variant(**{"Stock Length": "11'6\"", "Colour": "Galvanized", "Line": "ATL"})
        facts = atl._aa_raw_track_facts()
        self.assertEqual(facts, {"kind": "horizontal", "size": "3", "inches": 138,
                                 "colour": "Galvanized", "line": "atl"})
        black = self._variant(**{"Stock Length": "15'6\"", "Colour": "Black", "Line": "CHI"})
        self.assertEqual(black._aa_raw_track_facts()["inches"], 186)
        # and a prepared-track reader still refuses it
        self.assertIsNone(black._aa_track_facts())

    def test_a_bom_line_follows_its_raw_piece(self):
        made = self._family()
        old = made['3" Horizontal Track RAW - 9\'6" White'].product_variant_id
        prepared = self._product('3" Horizontal Track - 108" White')
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": prepared.id,
            "bom_line_ids": [(0, 0, {"product_id": old.id, "product_qty": 2})],
        })
        self._merge()
        self.assertEqual(
            bom.bom_line_ids.product_id,
            self._variant(**{"Stock Length": "9'6\"", "Colour": "White", "Line": "CHI"}))

    def test_a_family_with_no_atl_has_no_line_choice(self):
        for length in ("7'4\"", "9'4\""):
            for colour in ("Black", "White"):
                self._product('2" Vertical Track RAW - %s %s' % (length, colour), stock=1.0)
        reports = self.env["product.template"]._aa_merge_variant_families(
            dry_run=False, only=['2" Vertical Track RAW'])
        self.assertEqual(reports[0]["state"], "merged", reports)
        survivor = self.env["product.template"].search([("name", "=", '2" Vertical Track RAW')])
        self.assertEqual(sorted(survivor.attribute_line_ids.attribute_id.mapped("name")),
                         ["Colour", "Stock Length"])

    def test_the_rehearsal_changes_nothing(self):
        made = self._family()
        report = self._merge(dry_run=True)
        self.assertEqual(report["state"], "rehearsed", report)
        self.assertTrue(all(t.active for t in made.values()))
        self.assertFalse(self.env["product.template"].search([("name", "=", self.SURVIVOR)]))

    def test_running_it_again_does_nothing(self):
        self._family()
        self._merge()
        self.assertEqual(self._merge()["state"], "already merged")

    # --- what other modules keep on the piece ----------------------------

    def test_each_piece_keeps_its_aa_part_number(self):
        if "aa_part_number" not in self.env["product.product"]._fields:
            self.skipTest("aa_part_numbers is not installed")
        made = self._family()
        before = {name: t.product_variant_id.aa_part_number for name, t in made.items()}
        self.assertTrue(all(before.values()), before)
        self._merge()
        atl = self._variant(**{"Stock Length": "10'6\"", "Colour": "Galvanized", "Line": "ATL"})
        black = self._variant(**{"Stock Length": "9'6\"", "Colour": "Black", "Line": "CHI"})
        self.assertEqual(atl.aa_part_number,
                         before['3" Horizontal Track RAW - 10\'6" Galvanized ATL'])
        self.assertEqual(black.aa_part_number,
                         before['3" Horizontal Track RAW - 9\'6" Black'])

    def test_the_atl_angle_comes_down_to_its_own_length(self):
        if "aa_variant_prep_part_id" not in self.env["product.product"]._fields:
            self.skipTest("aa_order_coverage is not installed")
        made = self._family()
        angles = {}
        for length in ("10'6\"", "11'6\""):
            angle = self._product("2x2 Angle ATL (%s)" % length)
            angles[length] = angle.product_variant_id
            made['3" Horizontal Track RAW - %s Galvanized ATL' % length].write({
                "aa_hw_line": "atl",
                "aa_prep_part_id": angle.product_variant_id.id,
                "aa_prep_note": "ATL horizontal: bolt the 2x2 angle on",
            })
        self._merge()
        for length, angle in angles.items():
            atl = self._variant(**{"Stock Length": length, "Colour": "Galvanized",
                                   "Line": "ATL"})
            part, per = atl._aa_prep_part()
            self.assertEqual(part, angle)
            self.assertEqual(per, 1.0)
            self.assertIn("2x2", atl._aa_prep_note())
        chi = self._variant(**{"Stock Length": "10'6\"", "Colour": "Galvanized", "Line": "CHI"})
        self.assertFalse(chi._aa_prep_part()[0])
        self.assertFalse(chi._aa_prep_note())

    def test_chi_and_atl_pair_inside_the_product(self):
        if "aa_variant_prep_part_id" not in self.env["product.product"]._fields:
            self.skipTest("aa_order_coverage is not installed")
        self._family()
        self._merge()
        chi = self._variant(**{"Stock Length": "11'6\"", "Colour": "Galvanized", "Line": "CHI"})
        atl = self._variant(**{"Stock Length": "11'6\"", "Colour": "Galvanized", "Line": "ATL"})
        self.assertEqual(chi._aa_line(), "chi")
        self.assertEqual(atl._aa_line(), "atl")
        self.assertEqual(chi._aa_line_twin(), atl)
        self.assertEqual(atl._aa_line_twin(), chi)
        # a length ATL never made has no twin - the archived hole is not one
        lonely = self._variant(**{"Stock Length": "9'6\"", "Colour": "Galvanized", "Line": "CHI"})
        self.assertFalse(lonely._aa_line_twin())
