"""CUT IT FROM A LONGER RAW TRACK (owner, 2026-11-11).

Same size, same kind, same colour, longer, and on the rack; the job then
consumes that piece instead, and the leftover is thrown away.
"""

import unittest

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TrackSwapCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.stock = self.env.ref("stock.warehouse0").lot_stock_id
        self.wanted = self._raw("3\" Vertical Track RAW - 7'4\" Black", 0)
        self.longer = self._raw("3\" Vertical Track RAW - 9'6\" Black", 3)
        self.longest = self._raw("3\" Vertical Track RAW - 12' Black", 1)
        # Each wrong in one way only.
        self.shorter = self._raw("3\" Vertical Track RAW - 6' Black", 5)
        self.white = self._raw("3\" Vertical Track RAW - 10' White", 5)
        self.horizontal = self._raw("3\" Horizontal Track RAW - 11'6\" Black", 5)
        self.two_inch = self._raw("2\" Vertical Track RAW - 10' Black", 5)
        self.none_left = self._raw("3\" Vertical Track RAW - 8' Black", 0)
        self.finished = self.env["product.product"].create({
            "name": "Swap Test Vertical Track", "type": "consu", "is_storable": True})

    def _raw(self, name, on_hand):
        product = self.env["product.product"].create({
            "name": name, "type": "consu", "is_storable": True})
        if on_hand:
            self.env["stock.quant"]._update_available_quantity(product, self.stock, on_hand)
        return product

    def _job(self, component=None):
        component = component or self.wanted
        job = self.env["mrp.production"].create({
            "product_id": self.finished.id,
            "product_qty": 1.0,
            "move_raw_ids": [(0, 0, {
                "product_id": component.id,
                "product_uom_qty": 1.0,
            })],
        })
        job.action_confirm()
        return job

    def test_it_offers_longer_matching_pieces_on_the_rack_shortest_first(self):
        options = self._job().aa_track_swap_options()
        self.assertEqual([o["id"] for o in options["options"]], [self.longer.id, self.longest.id])
        self.assertEqual(options["options"][0]["length"], "9'6\"")
        self.assertEqual(options["needs"], 1.0)

    def test_the_swap_takes_the_longer_piece_off_the_count(self):
        job = self._job()
        job.aa_track_swap(self.longer.id)
        open_moves = job.move_raw_ids.filtered(lambda m: m.state != "cancel")
        self.assertEqual(open_moves.product_id, self.longer)
        self.assertEqual(open_moves.product_uom_qty, 1.0)
        self.assertEqual(open_moves.state, "assigned", "the piece on the rack is reserved for it")
        self.assertTrue(job.move_raw_ids.filtered(
            lambda m: m.product_id == self.wanted and m.state == "cancel"))
        self.assertIn("leftover is discarded", job.message_ids[0].body)

        job.move_raw_ids.filtered(lambda m: m.state != "cancel").picked = True
        job.qty_producing = 1.0
        job.button_mark_done()
        self.assertEqual(self.longer.qty_available, 2.0, "one 9'6\" piece used up")
        self.assertEqual(self.wanted.qty_available, 0.0)

    def test_a_piece_that_does_not_fit_is_refused_by_the_server(self):
        job = self._job()
        for wrong in (self.shorter, self.white, self.horizontal, self.two_inch):
            with self.assertRaises(UserError):
                job.aa_track_swap(wrong.id)

    def test_a_finished_job_cannot_be_changed(self):
        job = self._job(self.longer)
        job.move_raw_ids.picked = True
        job.qty_producing = 1.0
        job.button_mark_done()
        self.assertFalse(job.aa_track_swappable)
        with self.assertRaises(UserError):
            job.aa_track_swap(self.longest.id)

    def test_a_job_with_no_raw_track_has_no_button(self):
        job = self._job(self.finished)
        self.assertFalse(job.aa_track_swappable)
        self.assertEqual(job.aa_track_swap_board(), [])

    def test_a_custom_length_job_is_given_a_piece_for_each_side(self):
        custom = self.env.ref("aa_dealer_orders.product_custom_track", raise_if_not_found=False)
        if not custom:
            raise unittest.SkipTest("aa_dealer_orders is not installed")
        order = self.env["sale.order"].create({
            "partner_id": self.env["res.partner"].create({"name": "Swap Dealer"}).id,
            "order_line": [(0, 0, {
                "product_id": custom.product_variant_id.id,
                "product_uom_qty": 1.0,
                "name": '3" vertical, 100" long (Black) - custom length, AA prepares it',
                "price_unit": 200.0,
            })],
        })
        order.action_confirm()
        job = self.env["mrp.production"].search([("aa_sale_line_id", "in", order.order_line.ids)])
        self.assertTrue(job.aa_track_swappable)
        board = job.aa_track_swap_board()
        self.assertFalse(board[0]["current"])
        self.assertEqual(board[0]["needs"], 2.0, "LH + RH for the one pair")
        # 100" or more: the 9'6" (114") and the 12', not the 8' (96").
        self.assertEqual([o["id"] for o in board[0]["options"]], [self.longer.id, self.longest.id])
        job.aa_track_swap(self.longer.id)
        move = job.move_raw_ids.filtered(lambda m: m.product_id == self.longer)
        self.assertEqual(move.product_uom_qty, 2.0, "LH + RH for the one pair")

    def test_both_jobs_on_one_card_can_be_changed(self):
        vertical = self._job()
        horizontal_wanted = self._raw("3\" Horizontal Track RAW - 9'6\" Black", 0)
        horizontal = self._job(horizontal_wanted)
        board = (vertical | horizontal).aa_track_swap_board()
        self.assertEqual(len(board), 2)
        vertical.aa_track_swap(self.longer.id)
        horizontal.aa_track_swap(self.horizontal.id)
        self.assertEqual(vertical.move_raw_ids.filtered(lambda m: m.state != "cancel").product_id, self.longer)
        self.assertEqual(horizontal.move_raw_ids.filtered(lambda m: m.state != "cancel").product_id,
                         self.horizontal)
