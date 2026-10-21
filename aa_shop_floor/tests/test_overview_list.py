"""THE OVERVIEW AS A LIST (owner, 2026-10-21: more than 60 orders).

The list view draws every order as a row from the same order board the cards
read. An order with ONE job used to get no board at all ("grouped": False and
nothing else), which would have left it a row with no station and no buttons.
"""

import json

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class OverviewListCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "List Dealer"})
        self.order = self.env["sale.order"].create({"partner_id": self.partner.id})
        self.station = self.env["mrp.workcenter"].search(
            [("name", "!=", "Pending Assignment")], limit=1) \
            or self.env["mrp.workcenter"].create({"name": "Hardware"})
        self.product = self.env["product.product"].create({
            "name": "A box", "type": "consu", "is_storable": True})

    def _job(self, origin):
        production = self.env["mrp.production"].create({
            "product_id": self.product.id, "product_qty": 1.0, "origin": origin})
        self.env["mrp.workorder"].with_context(aa_keep_workcenter=True).create({
            "name": "Pack it", "production_id": production.id,
            "product_uom_id": production.product_uom_id.id,
            "workcenter_id": self.station.id})
        production.action_confirm()
        return production

    def _board(self, production):
        production.invalidate_recordset(["aa_order_board"])
        return json.loads(production.aa_order_board)

    def test_a_one_job_order_has_a_board_but_is_not_grouped(self):
        board = self._board(self._job(self.order.name))

        self.assertFalse(board["grouped"], "a one-job order is still drawn as a plain card")
        self.assertEqual(len(board["jobs"]), 1)
        self.assertEqual(board["customer"], "List Dealer")
        self.assertTrue(board["received_utc"].endswith("Z"))

    def test_a_two_job_order_is_grouped(self):
        first = self._job(self.order.name)
        self._job(self.order.name)

        self.assertTrue(self._board(first)["grouped"])

    def test_a_job_with_no_sale_order_has_no_board(self):
        board = self._board(self._job("Made by hand"))

        self.assertEqual(board, {"grouped": False})
