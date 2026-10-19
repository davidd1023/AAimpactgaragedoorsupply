"""A Springs order takes its inches off the right coil piece.

Owner, 2026-10-19: a leftover piece first if one is long enough, then the coils
on the floor, and the boxes last.
"""

import json

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.aa_spring_stock.models.coil import pick_piece, spring_cuts, coil_code


@tagged("post_install", "-at_install")
class CoilConsumptionCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        stock = cls.warehouse.lot_stock_id
        Location = env["stock.location"]

        def place(name):
            return Location.search([("name", "=", name), ("location_id", "=", stock.id)], limit=1) \
                or Location.create({"name": name, "location_id": stock.id, "usage": "internal"})

        cls.rack, cls.floor, cls.boxes = place("Rack"), place("Floor"), place("Boxes")
        inch = env["uom.uom"].search([("name", "=", "in")], limit=1) or env.ref("uom.product_uom_unit")
        cls.coil = {}
        for hand in ("L", "R"):
            code = "COIL-262-2.625-%s" % hand
            cls.coil[hand] = env["product.product"].search([("default_code", "=", code)], limit=1) \
                or env["product.product"].create({
                    "name": "Torsion Spring Coil 2 5/8\" (.262, %s) TEST" % hand,
                    "default_code": code,
                    "is_storable": True,
                    "tracking": "lot",
                    "uom_id": inch.id,
                })
        # Start from a clean slate for these coils.
        env["stock.quant"].search([("product_id", "in", [p.id for p in cls.coil.values()])]).sudo().unlink()

        cls.spring_tmpl = env.ref("spring_engineering.product_custom_spring")
        cls.bom = env["mrp.bom"]._aa_custom_spring_bom()

    def put(self, hand, lot_name, location, inches):
        product = self.coil[hand]
        lot = self.env["stock.lot"].create({"name": lot_name, "product_id": product.id})
        self.env["stock.quant"]._update_available_quantity(product, location, inches, lot_id=lot)
        return lot

    def on_hand(self, lot, location=None):
        domain = [("lot_id", "=", lot.id), ("location_id.usage", "=", "internal")]
        if location:
            domain.append(("location_id", "=", location.id))
        return sum(self.env["stock.quant"].search(domain).mapped("quantity"))

    def make_order(self, length=30.0, springs=2):
        lh = (springs + 1) // 2
        spec = {"assembly": "Single", "springs": springs, "lh": lh, "rh": springs - lh,
                "items": [{"role": "Spring", "wire": 0.2625, "id": 2.625, "length": length}]}
        production = self.env["mrp.production"].create({
            "product_id": self.spring_tmpl.product_variant_id.id,
            "product_qty": 1.0,
            "bom_id": self.bom.id,
            "picking_type_id": self.warehouse.manu_type_id.id,
            "aa_station_kind": "spring",
            "aa_spring_spec_json": json.dumps(spec),
        })
        production.action_confirm()
        return production

    # --- the pure rules -------------------------------------------------------

    def test_rules(self):
        self.assertEqual(coil_code(0.2625, 2.625, "L"), "COIL-262-2.625-L")
        self.assertEqual(coil_code(0.2437, 5.25, "R"), "COIL-243-5.25-R")
        self.assertIsNone(coil_code(0.2253, 3.75, "L"), "no coil that close to .2253")
        self.assertIsNone(coil_code(0.2625, 6.0, "L"), "no 6\" coils")
        pieces = [("Floor", 84, "f1", 1), ("Floor", 40, "f2", 2), ("Rack", 20, "r1", 3),
                  ("Rack", 35, "r2", 4), ("Rack", 50, "r3", 5), ("Boxes", 84, "b1", 6)]
        self.assertEqual(pick_piece(pieces, 30)[2], "r2", "shortest rack piece that fits")
        self.assertEqual(pick_piece(pieces, 60)[2], "f1", "no rack piece fits: floor")
        self.assertEqual(pick_piece(pieces, 38)[2], "r3")
        self.assertEqual(pick_piece([("Boxes", 84, "b1", 6)], 30)[2], "b1")
        self.assertIsNone(pick_piece(pieces, 90))
        duplex = {"lh": 1, "rh": 1, "items": [{"role": "Outer", "wire": 0.2625, "id": 6.0, "length": 32},
                                              {"role": "Inner", "wire": 0.2253, "id": 3.75, "length": 31}]}
        cuts = spring_cuts(duplex, 2)
        self.assertEqual(len(cuts), 8, "2 units x (1 LH + 1 RH) x outer + inner")
        self.assertEqual({c["hand"] for c in cuts if c["role"] == "Inner"}, {"L", "R"})

    # --- the whole order ------------------------------------------------------------

    def test_rack_first_then_floor(self):
        rack_l = self.put("L", "262-2.625-L-S01", self.rack, 32.0)
        floor_l = self.put("L", "262-2.625-1-L", self.floor, 84.0)
        floor_r = self.put("R", "262-2.625-1-R", self.floor, 84.0)
        short_r = self.put("R", "262-2.625-R-S02", self.rack, 12.0)

        production = self.make_order(length=30.0)
        cuts = production.aa_spring_cut_ids
        self.assertEqual(len(cuts), 2)
        self.assertEqual(cuts.filtered(lambda c: c.hand == "L").lot_id, rack_l)
        self.assertEqual(cuts.filtered(lambda c: c.hand == "R").lot_id, floor_r,
                         "the 12\" rack piece is too short")
        self.assertIn("262-2.625-L-S01", production.aa_shop_spec)

        # A second order cannot count on the inches the first one reserved.
        second = self.make_order(length=30.0)
        self.assertEqual(second.aa_spring_cut_ids.filtered(lambda c: c.hand == "L").lot_id, floor_l)

        production.button_mark_done()
        self.assertEqual(production.state, "done")
        self.assertAlmostEqual(self.on_hand(rack_l), 0.0, msg='2" left: scrapped (under 16")')
        self.assertIn("scrapped", cuts.filtered(lambda c: c.hand == "L").note)
        self.assertAlmostEqual(self.on_hand(floor_r), 54.0)
        self.assertAlmostEqual(self.on_hand(short_r), 12.0)
        self.assertEqual(set(cuts.mapped("state")), {"done"})
        self.assertAlmostEqual(cuts.filtered(lambda c: c.hand == "R").remaining, 54.0)

    def test_box_coil_is_opened_onto_the_floor(self):
        box_l = self.put("L", "BOX1-262-2.625-L-01", self.boxes, 84.0)
        box_r = self.put("R", "BOX1-262-2.625-R-01", self.boxes, 84.0)
        production = self.make_order(length=40.0)
        self.assertEqual(set(production.aa_spring_cut_ids.mapped("source")), {"Boxes"})
        production.button_mark_done()
        self.assertAlmostEqual(self.on_hand(box_l, self.floor), 44.0)
        self.assertAlmostEqual(self.on_hand(box_r, self.floor), 44.0)
        self.assertAlmostEqual(self.on_hand(box_l, self.boxes), 0.0)

    def test_a_16_inch_leftover_is_kept(self):
        rack_l = self.put("L", "262-2.625-L-S03", self.rack, 46.0)
        rack_r = self.put("R", "262-2.625-R-S04", self.rack, 45.0)
        production = self.make_order(length=30.0)
        production.button_mark_done()
        self.assertAlmostEqual(self.on_hand(rack_l, self.rack), 16.0, msg="16\" stays on the rack")
        self.assertAlmostEqual(self.on_hand(rack_r), 0.0, msg="15\" is scrapped")

    def test_no_coil_never_blocks(self):
        production = self.make_order(length=30.0)
        self.assertEqual(set(production.aa_spring_cut_ids.mapped("state")), {"short"})
        self.assertIn("NO COIL", production.aa_shop_spec)
        production.button_mark_done()
        self.assertEqual(production.state, "done")

    def test_summary(self):
        self.put("L", "262-2.625-1-L", self.floor, 84.0)
        self.put("R", "262-2.625-1-R", self.floor, 84.0)
        self.put("R", "262-2.625-R-S09", self.rack, 20.0)
        self.env.flush_all()
        row = self.env["aa.spring.stock.summary"].search([("wire", "=", "262"), ("inside_diameter_num", "=", 2.625)])
        self.assertEqual(row.floor_pairs, 1)
        self.assertEqual(row.rack_r_pcs, 1)
        self.assertEqual(row.alert, "order", "one pair on the floor and nothing in the boxes")
