"""A TRACK LONGER THAN ANY PREPARED ONE GETS A TRACK PREP JOB (owner, 2026-11-11).

W/O #383, a 12' x 12' door: its tracks went on the order as two custom-length
lines (156" horizontal, 136" vertical) that AA prepares, and the Overview said
"-" under Track Prep, because only the stock lengths ever had a job.
"""

import unittest

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class CustomTrackJobCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.custom = self.env.ref("aa_dealer_orders.product_custom_track", raise_if_not_found=False)
        if not self.custom:
            raise unittest.SkipTest("aa_dealer_orders is not installed: no custom tracks to prepare")
        self.partner = self.env["res.partner"].create({"name": "Custom Track Dealer"})

    def _order(self, *names, qty=1.0):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.custom.product_variant_id.id,
                "product_uom_qty": qty,
                "name": name,
                "price_unit": 200.0,
            }) for name in names],
        })
        return order

    def _jobs(self, order):
        return self.env["mrp.production"].search([("aa_sale_line_id", "in", order.order_line.ids)])

    def _rows(self, job):
        return dict(row.split("|")[:2] for row in (job.aa_shop_spec or "").split("\n") if "|" in row)

    HORIZONTAL = ('3" horizontal, 156" long (Black) - custom length, AA prepares it '
                  '(priced per inch from the 132" track)\nTracks for Door 1')
    VERTICAL = ('3" vertical, 136" long (Black) - custom length, AA prepares it '
                '(priced per inch from the 112" track)\nTracks for Door 1 (Hunters Rd)')

    def test_confirming_the_order_puts_each_track_on_track_prep(self):
        order = self._order(self.HORIZONTAL, self.VERTICAL)
        order.action_confirm()

        jobs = self._jobs(order)
        self.assertEqual(len(jobs), 2, "one Track Prep job per custom-length line")
        self.assertEqual(set(jobs.mapped("aa_station_kind")), {"track"})
        for job in jobs:
            stations = job.workorder_ids.mapped(lambda w: w._aa_own_station().name)
            self.assertEqual(stations, ["Track Prep"])
            # The job makes the never-stocked placeholder, never the service line.
            self.assertEqual(job.product_id.product_tmpl_id,
                             self.env.ref("aa_shop_floor.product_custom_track_job"))
            self.assertEqual(job.origin, order.name)

    def test_the_card_says_what_to_cut(self):
        order = self._order(self.VERTICAL)
        order.action_confirm()
        rows = self._rows(self._jobs(order))
        self.assertEqual(rows["Track"], '3" Vertical · Black')
        self.assertEqual(rows["Cut to"], '136" (LH + RH)')
        self.assertEqual(rows["Pairs"], "1")
        self.assertEqual(rows["For"], "Door 1 (Hunters Rd)")

    def test_two_doors_cut_two_pairs(self):
        order = self._order(self.HORIZONTAL, qty=2.0)
        order.action_confirm()
        self.assertEqual(self._rows(self._jobs(order))["Pairs"], "2")

    def test_a_line_written_another_way_still_gets_a_card(self):
        order = self._order("Custom track per drawing\nTracks for Door 1")
        order.action_confirm()
        rows = self._rows(self._jobs(order))
        self.assertEqual(rows["Track"], "Custom track per drawing")

    def test_confirming_twice_makes_nothing_twice(self):
        order = self._order(self.HORIZONTAL)
        order.action_confirm()
        order._aa_create_station_productions()
        self.assertEqual(len(self._jobs(order)), 1)

    def test_only_limits_what_an_old_order_is_given(self):
        kit = self.env["product.template"].create({
            "name": "Custom Track Test Hardware Kit", "type": "consu", "is_storable": True,
            "list_price": 100.0, "sale_ok": True})
        order = self._order(self.HORIZONTAL)
        order.write({"order_line": [(0, 0, {"product_id": kit.product_variant_id.id, "product_uom_qty": 1})]})
        # An order confirmed before this version, with no jobs at all: the
        # migration hands it `only=("track",)`.
        order._aa_create_station_productions(only=("track",))
        self.assertEqual(self._jobs(order).mapped("aa_station_kind"), ["track"],
                         "the migration path raises the track job and nothing else")

    def test_removing_the_tracks_cancels_the_job(self):
        if not hasattr(self.env["sale.order"], "aa_remove_part"):
            raise unittest.SkipTest("aa_dealer_orders' remove part is not installed")
        order = self._order(self.HORIZONTAL)
        order.action_confirm()
        job = self._jobs(order)
        self.assertTrue(order._aa_part_jobs(order._aa_track_lines()) & job,
                        "Remove Tracks finds the custom track's job by its sale line")
