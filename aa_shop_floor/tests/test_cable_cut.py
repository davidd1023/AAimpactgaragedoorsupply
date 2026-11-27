"""Lift cables cut, deducted and charged by the AA calculator (owner, 2026-11-27)."""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class CableCutCase(TransactionCase):

    def setUp(self):
        super().setUp()
        foot = self.env.ref("uom.product_uom_foot")
        Product = self.env["product.product"]
        self.reel = Product.create({"name": "5/32\" 7x19 Cable 500ft Reel (cut test)", "type": "consu",
                                    "is_storable": True, "uom_id": foot.id, "standard_price": 0.10})
        self.sleeve = Product.create({"name": "Oval sleeve (cut test)", "type": "consu", "standard_price": 0.05})
        self.pair = Product.create({
            "name": "Lift Cable 5/32\" Pair - Prepared (9' Door, 3\" Track (15R))",
            "type": "consu", "list_price": 30.0})
        self.env["mrp.bom"].create({
            "product_tmpl_id": self.pair.product_tmpl_id.id, "product_id": self.pair.id,
            "type": "phantom", "product_qty": 1.0,
            "bom_line_ids": [(0, 0, {"product_id": self.reel.id, "product_qty": 21.5, "product_uom_id": foot.id}),
                             (0, 0, {"product_id": self.sleeve.id, "product_qty": 2.0})]})
        self.kit = Product.create({"name": "AA-1600 Hardware Kit (cut test)", "type": "consu", "list_price": 100})
        partner = self.env["res.partner"].create({"name": "Cut test dealer"})
        self.order = self.env["sale.order"].create({"partner_id": partner.id})
        self.kit_line = self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": self.kit.id, "product_uom_qty": 1,
            "aa_door_height_in": 98})
        if "aa_drum" in self.kit_line._fields:
            self.kit_line.write({"aa_drum": "D400-144", "aa_track_type": "3-15R", "aa_lift_type": "standard"})
        else:
            self.skipTest("aa_dealer_orders is not installed: no drum on the kit line")
        self.cable_line = self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": self.pair.id, "product_uom_qty": 1,
            "linked_line_id": self.kit_line.id})

    def test_the_cut_is_the_calculators_not_the_nine_foot_pair(self):
        # 98" 3" 15R D400-144: (98 - 8) + 17 + 3 1/8 + 8 -> 119" (the pair says 129").
        self.assertEqual(self.cable_line._aa_cable_cut_calc(), 119.0)

    def test_the_price_follows_the_length(self):
        # cost at 21.5 ft: 2.15 + 0.10 = 2.25; at 2 x 119" = 19.833 ft: 1.9833 + 0.10.
        expected = 30.0 * (19.8333333 * 0.10 + 0.10) / 2.25
        self.assertAlmostEqual(self.cable_line.price_unit, expected, places=2)

    def test_the_reel_goes_out_at_the_calculated_length(self):
        self.order.action_confirm()
        reel_moves = self.order.picking_ids.move_ids.filtered(lambda m: m.product_id == self.reel)
        self.assertTrue(reel_moves)
        # Every leg of the delivery takes the same feet: 2 x 119" = 19.83 ft, not 21.5.
        for move in reel_moves:
            self.assertAlmostEqual(move.product_uom_qty, 2 * 119 / 12.0, places=2)
