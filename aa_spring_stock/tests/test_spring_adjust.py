"""Floor / Rack / Boxes is where the spring stock is worked (owner, 2026-10-20).

Move coils from a box to the floor from that page, and fix the pieces there when
springs were used without the system knowing. Empty boxes close by themselves.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.aa_spring_stock.tests.test_coil_consumption import CoilStockMixin


@tagged("post_install", "-at_install")
class SpringAdjustCase(CoilStockMixin, TransactionCase):

    def row(self, place, box=None):
        self.env.flush_all()
        domain = [("place", "=", place), ("wire", "=", "262"), ("inside_diameter_num", "=", 2.625)]
        if box:
            domain.append(("box_id", "=", box.id))
        return self.env["aa.spring.place.summary"].search(domain)

    def add_box(self, number, lh, rh):
        wizard = self.env["aa.spring.box.add"].create({
            "new_box_number": number,
            "line_ids": [(0, 0, {"inside_diameter": "2.625", "wire": "262", "l_qty": lh, "r_qty": rh})],
        })
        wizard.action_confirm()
        return self.env["aa.spring.box"].search([("number", "=", number), ("state", "=", "open")])

    def test_add_coils_starts_a_new_box(self):
        box = self.add_box(91, 2, 1)
        self.assertTrue(box)
        self.assertEqual((box.l_coils, box.r_coils), (2, 1))

    def test_move_to_floor_from_the_row_closes_the_empty_box(self):
        box = self.add_box(92, 2, 1)
        action = self.row("Boxes", box).action_move_to_floor()
        wizard = self.env["aa.spring.box.move"].browse(action["res_id"])
        self.assertEqual(sorted(wizard.line_ids.mapped("available")), [1, 2])
        wizard.action_all()
        self.assertEqual(self.row("Floor").l_pcs, 2)
        self.assertEqual(box.state, "closed", "an empty box closes by itself")

    def test_adjust_changes_removes_and_adds_pieces(self):
        a = self.put("L", "TEST-ADJ-A-L", self.floor, 60.0)
        b = self.put("L", "TEST-ADJ-B-L", self.floor, 40.0)
        action = self.row("Floor").action_adjust()
        wizard = self.env["aa.spring.adjust"].browse(action["res_id"])
        self.assertEqual(len(wizard.line_ids), 2)
        wizard.line_ids.filtered(lambda l: l.lot_id == a).new_qty = 25.0
        wizard.line_ids.filtered(lambda l: l.lot_id == b).new_qty = 0.0
        wizard.line_ids = [(0, 0, {"hand": "R", "new_qty": 84.0})]
        wizard.action_apply()
        self.assertAlmostEqual(self.on_hand(a, self.floor), 25.0)
        self.assertAlmostEqual(self.on_hand(b), 0.0)
        row = self.row("Floor")
        self.assertEqual((row.l_pcs, row.r_pcs), (1, 1))
        self.assertAlmostEqual(row.r_in, 84.0)

    def test_adjust_cannot_go_below_a_reservation(self):
        lot = self.put("L", "TEST-ADJ-RES-L", self.floor, 50.0)
        self.put("R", "TEST-ADJ-RES-R", self.floor, 50.0)
        self.make_order(length=30.0)
        action = self.row("Floor").action_adjust()
        wizard = self.env["aa.spring.adjust"].browse(action["res_id"])
        wizard.line_ids.filtered(lambda l: l.lot_id == lot).new_qty = 10.0
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_adjust_a_box_to_empty_closes_it(self):
        box = self.add_box(93, 1, 0)
        action = self.row("Boxes", box).action_adjust()
        wizard = self.env["aa.spring.adjust"].browse(action["res_id"])
        wizard.line_ids.new_qty = 0.0
        wizard.action_apply()
        self.assertEqual(box.state, "closed")
