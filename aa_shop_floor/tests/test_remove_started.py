"""REMOVE TAKES BACK A STARTED JOB TOO (owner, 2026-11-26).

"una vez que admin quite la orden debe volver a como estaba antes de mandarse,
nada se debera ver en las estaciones" - a job the worker had already started
stayed on his station after Remove.
"""

from datetime import datetime

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class RemoveStartedCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.manager = new_test_user(
            self.env, login="aa_remove_manager", groups="base.group_user,mrp.group_mrp_manager")
        self.product = self.env["product.product"].create(
            {"name": "Remove test track", "type": "consu", "is_storable": True})
        self.station = self.env["mrp.workcenter"].create({"name": "Remove Test Bench"})
        self.pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        self.production = self.env["mrp.production"].create(
            {"product_id": self.product.id, "product_qty": 1.0, "origin": "S-REMOVE"})
        self.workorder = self.env["mrp.workorder"].create({
            "name": "Cut it", "production_id": self.production.id,
            "workcenter_id": self.station.id, "product_uom_id": self.product.uom_id.id})
        loss = self.env["mrp.workcenter.productivity.loss"].search(
            [("loss_id.loss_type", "=", "productive")], limit=1)
        self.env["mrp.workcenter.productivity"].create({
            "workorder_id": self.workorder.id, "workcenter_id": self.station.id,
            "loss_id": loss.id, "date_start": datetime(2026, 11, 26, 15, 0)})
        self.workorder.state = "progress"

    def test_a_started_job_goes_back_to_pending_with_its_clock_cleared(self):
        self.production.with_user(self.manager).aa_remove_from_station()
        self.assertEqual(self.workorder.workcenter_id, self.pending)
        self.assertEqual(self.workorder.state, "ready")
        self.assertFalse(self.workorder.time_ids)
        self.assertEqual(self.workorder.aa_suggested_workcenter_id, self.station,
                         "Send puts it back on the same station")
