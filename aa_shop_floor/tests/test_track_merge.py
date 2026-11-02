"""ONE TRACK TASK PER ORDER AT THE STATION (owner, 2026-11-02).

"cada vez que mando un track a jorge me salen dos tareas por separadas para la
misma orden, una para el vertical y otra para el horizontal, juntame las dos"
"""

import json

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TrackMergeCase(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env["res.partner"].create({"name": "Merge Dealer"})
        self.order = self.env["sale.order"].create({"partner_id": partner.id})
        Workcenter = self.env["mrp.workcenter"]
        self.tracks = Workcenter.search([("name", "=", "Track Prep")], limit=1) \
            or Workcenter.create({"name": "Track Prep"})
        self.hardware = Workcenter.search([("name", "=", "Hardware")], limit=1) \
            or Workcenter.create({"name": "Hardware"})
        self.vertical = self.env["product.product"].create({
            "name": "Merge Vertical Track", "type": "consu", "is_storable": True})
        self.horizontal = self.env["product.product"].create({
            "name": "Merge Horizontal Track", "type": "consu", "is_storable": True})

    def _job(self, product, station, origin=None):
        production = self.env["mrp.production"].create({
            "product_id": product.id, "product_qty": 1.0,
            "origin": origin or self.order.name})
        self.env["mrp.workorder"].with_context(aa_keep_workcenter=True).create({
            "name": "Cut tracks", "production_id": production.id,
            "product_uom_id": production.product_uom_id.id,
            "workcenter_id": station.id})
        production.action_confirm()
        return production

    def _merge(self, production):
        wo = production.workorder_ids[:1]
        wo.invalidate_recordset(["aa_track_merge"])
        return json.loads(wo.aa_track_merge)

    def test_vertical_and_horizontal_are_one_card(self):
        first = self._job(self.vertical, self.tracks)
        second = self._job(self.horizontal, self.tracks)

        carrier = self._merge(first)
        self.assertFalse(carrier["hidden"])
        self.assertEqual([p["production_id"] for p in carrier["partners"]], [second.id])
        self.assertEqual(carrier["partners"][0]["product"], "Merge Horizontal Track")
        self.assertTrue(self._merge(second)["hidden"], "the second track job is drawn on the first card")

    def test_a_single_track_job_is_its_own_card(self):
        merge = self._merge(self._job(self.vertical, self.tracks))
        self.assertEqual(merge, {"hidden": False, "partners": []})

    def test_another_orders_track_is_not_merged(self):
        first = self._job(self.vertical, self.tracks)
        other = self.env["sale.order"].create({"partner_id": self.order.partner_id.id})
        self._job(self.horizontal, self.tracks, origin=other.name)
        self.assertEqual(self._merge(first)["partners"], [])

    def test_hardware_jobs_are_not_merged(self):
        first = self._job(self.vertical, self.hardware)
        self._job(self.horizontal, self.hardware)
        self.assertEqual(self._merge(first), {"hidden": False, "partners": []})

    def test_a_job_not_yet_at_the_station_is_not_merged(self):
        first = self._job(self.vertical, self.tracks)
        self._job(self.horizontal, self.hardware)  # elsewhere, e.g. still pending
        self.assertEqual(self._merge(first)["partners"], [])

    def test_finishing_the_card_finishes_both(self):
        first = self._job(self.vertical, self.tracks)
        second = self._job(self.horizontal, self.tracks)

        first._set_quantities()
        first.with_context(skip_consumption=True, skip_backorder=True,
                           mo_ids_to_backorder=[]).button_mark_done()

        self.assertEqual(first.state, "done")
        self.assertEqual(second.state, "done", "the merged track job closes with its card")

    def test_the_manager_closing_both_does_not_trip(self):
        first = self._job(self.vertical, self.tracks)
        second = self._job(self.horizontal, self.tracks)

        (first | second).with_user(self.env.ref("base.user_admin")).aa_mark_done_jobs()

        self.assertEqual((first | second).mapped("state"), ["done", "done"])
