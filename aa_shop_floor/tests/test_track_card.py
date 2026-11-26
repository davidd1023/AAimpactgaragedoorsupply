"""JORGE'S TRACK CARD, STRAIGHT TO THE POINT (owner, 2026-11-26).

What to take, what to cut it to, the lift, and jamb brackets per vertical.
"""

import json

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TrackCardCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.stock = self.env.ref("stock.warehouse0").lot_stock_id
        Product = self.env["product.product"]
        self.raw_h = Product.create({"name": "3\" Horizontal Track RAW - 9'6\" Black",
                                     "type": "consu", "is_storable": True})
        self.raw_v = Product.create({"name": "3\" Vertical Track RAW - 7'4\" Black",
                                     "type": "consu", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(self.raw_h, self.stock, 5)
        self.horizontal = Product.create({"name": "3\" Horizontal Track - 108\" Black",
                                          "type": "consu", "is_storable": True})
        self.vertical = Product.create({"name": "3\" Vertical Track (Black, 88\" - 8' Door Height)",
                                        "type": "consu", "is_storable": True})
        self.jamb10 = Product.create({"name": "Jamb Bracket (Black, #10)", "type": "consu"})
        self.jamb12 = Product.create({"name": "Jamb Bracket (Black, #12)", "type": "consu"})

    def _job(self, product, pairs, components):
        job = self.env["mrp.production"].create({
            "product_id": product.id,
            "product_qty": pairs,
            "move_raw_ids": [(0, 0, {"product_id": p.id, "product_uom_qty": q}) for p, q in components],
        })
        job.action_confirm()
        return job

    def _card(self, job):
        job.invalidate_recordset(["aa_track_card"])
        return json.loads(job.aa_track_card)

    def test_a_horizontal_says_what_to_take_and_what_to_cut_it_to(self):
        card = self._card(self._job(self.horizontal, 2, [(self.raw_h, 4)]))
        self.assertEqual(card["kind"], "horizontal")
        self.assertEqual(card["take_length"], "9'6\"")
        self.assertEqual(card["take_qty"], "4")
        self.assertTrue(card["cut"])
        self.assertEqual(card["length"], '108"')
        self.assertFalse(card["short"], "5 on hand covers 4")
        self.assertEqual(card["jambs"], [])

    def test_a_vertical_used_as_it_comes_with_jambs_per_vertical(self):
        job = self._job(self.vertical, 2, [(self.raw_v, 4), (self.jamb10, 16), (self.jamb12, 16)])
        card = self._card(job)
        self.assertEqual(card["kind"], "vertical")
        self.assertFalse(card["cut"], "a 7'4\" RAW piece is already 88\"")
        self.assertTrue(card["short"], "none of that RAW on the rack")
        self.assertEqual(card["door"], "8'")
        self.assertEqual(card["jambs"], [{"name": "#10", "per": "4"}, {"name": "#12", "per": "4"}])

    def test_something_that_is_not_a_track_has_no_card(self):
        job = self._job(self.jamb10, 1, [(self.jamb12, 1)])
        self.assertFalse(job.aa_track_card)
