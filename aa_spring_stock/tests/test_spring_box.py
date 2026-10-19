"""Numbered spring boxes (owner, 2026-10-19).

Springs come in big boxes and stay in them until the floor has room. A box can
hold several sizes; coils go down to the floor a few at a time; an empty box is
removed. A Springs order still takes from the boxes last.
"""

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.aa_spring_stock.tests.test_coil_consumption import CoilStockMixin


@tagged("post_install", "-at_install")
class SpringBoxCase(CoilStockMixin, TransactionCase):

    def add(self, box, *lines):
        wizard = self.env["aa.spring.box.add"].create({
            "box_id": box.id,
            "line_ids": [(0, 0, {"inside_diameter": i, "wire": w, "l_qty": l, "r_qty": r})
                         for i, w, l, r in lines],
        })
        wizard.action_confirm()

    def box_coils(self, box, code):
        return self.env["stock.quant"].search([
            ("location_id", "=", box.location_id.id), ("product_id.default_code", "=", code),
            ("quantity", ">", 0)])

    def test_box_lifecycle(self):
        Box = self.env["aa.spring.box"]
        box = Box.create({"number": 97})
        self.assertEqual(box.location_id.name, "Box 97")
        self.assertEqual(box.location_id.location_id, self.boxes)
        with self.assertRaises(ValidationError):
            Box.create({"number": 97})

        # Several sizes in one box.
        self.add(box, ("2.625", "262", 3, 2), ("5.25", "406", 1, 1))
        quants = self.box_coils(box, "COIL-262-2.625-L")
        self.assertEqual(len(quants), 3, "one lot per coil")
        self.assertEqual(set(quants.mapped("quantity")), {84.0})
        self.assertEqual(sorted(quants.lot_id.mapped("name")),
                         ["BOX97-262-2.625-L-01", "BOX97-262-2.625-L-02", "BOX97-262-2.625-L-03"])
        self.assertTrue(self.env["product.product"].search([("default_code", "=", "COIL-406-5.25-R")]))
        box.invalidate_recordset()
        self.assertEqual((box.l_coils, box.r_coils), (4, 3))

        # Adding more keeps numbering the lots.
        self.add(box, ("2.625", "262", 1, 0))
        self.assertIn("BOX97-262-2.625-L-04", self.box_coils(box, "COIL-262-2.625-L").lot_id.mapped("name"))

        self.env.flush_all()
        rows = self.env["aa.spring.place.summary"].search([("box_id", "=", box.id)])
        row = rows.filtered(lambda r: r.wire == "262")
        self.assertEqual((row.place, row.l_pcs, row.r_pcs, row.pairs), ("Boxes", 4, 2, 2))
        summary = self.env["aa.spring.stock.summary"].search(
            [("wire", "=", "262"), ("inside_diameter_num", "=", 2.625)])
        self.assertEqual(summary.boxes_l_pcs, 4, "a numbered box still counts as Boxes")

        # Cannot remove a box with coils in it.
        with self.assertRaises(UserError):
            box.action_remove()

        # Two LH coils to the floor.
        action = box.action_move_to_floor()
        move = self.env["aa.spring.box.move"].browse(action["res_id"])
        line = move.line_ids.filtered(lambda l: l.product_id.default_code == "COIL-262-2.625-L")
        self.assertEqual(line.available, 4)
        line.qty = 2
        move.action_confirm()
        self.assertEqual(len(self.box_coils(box, "COIL-262-2.625-L")), 2)
        self.env.flush_all()
        floor = self.env["aa.spring.place.summary"].search(
            [("place", "=", "Floor"), ("wire", "=", "262"), ("inside_diameter_num", "=", 2.625)])
        self.assertEqual(floor.l_pcs, 2)

        # Everything else, then the empty box goes away.
        action = box.action_move_to_floor()
        self.env["aa.spring.box.move"].browse(action["res_id"]).action_all()
        box.invalidate_recordset()
        self.assertTrue(box.is_empty)
        box.action_remove()
        self.assertEqual(box.state, "closed")
        self.assertFalse(box.location_id.active)
        # The number can be used again.
        again = Box.create({"number": 97})
        self.add(again, ("2.625", "262", 1, 0))
        self.assertEqual(self.box_coils(again, "COIL-262-2.625-L").lot_id.name, "BOX97-262-2.625-L-05")

    def test_orders_take_box_coils_last(self):
        box = self.env["aa.spring.box"].create({"number": 98})
        self.add(box, ("2.625", "262", 1, 1))
        floor_l = self.put("L", "TEST-262-2.625-F98-L", self.floor, 40.0)
        production = self.make_order(length=30.0)
        cuts = production.aa_spring_cut_ids
        self.assertEqual(cuts.filtered(lambda c: c.hand == "L").lot_id, floor_l)
        right = cuts.filtered(lambda c: c.hand == "R")
        self.assertEqual(right.source, "Boxes")
        production.button_mark_done()
        self.assertAlmostEqual(self.on_hand(right.lot_id, self.floor), 54.0, msg="opened box coil goes to the floor")

    def test_loose_box_coils_are_adopted(self):
        lot = self.put("L", "BOX99-262-2.625-L-01", self.boxes, 84.0)
        self.env["aa.spring.box"]._aa_adopt_loose_box_coils()
        box = self.env["aa.spring.box"].search([("number", "=", 99), ("state", "=", "open")])
        self.assertTrue(box)
        self.assertAlmostEqual(self.on_hand(lot, box.location_id), 84.0)
