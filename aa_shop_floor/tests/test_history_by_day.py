"""HISTORY BY DAY (owner, 2026-10-21): everything finished on one day, the
orders separated by the day their parts were finished."""

from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests.common import tagged

from .test_shop_floor_history import ShopFloorHistoryCase


@tagged("post_install", "-at_install")
class HistoryByDayCase(ShopFloorHistoryCase):

    def setUp(self):
        super().setUp()
        today = fields.Date.today()
        self.today = datetime.combine(today, time(14, 0))
        self.yesterday = self.today - timedelta(days=1)

    def _done(self, order, station, product, at):
        start = at - timedelta(minutes=30)
        return self._job(order, station, product, logs=[(start, at)],
                         started=start, finished=at)

    def _by_day(self, days=30):
        return self.env["mrp.workorder"].aa_shop_floor_history_by_day(days=days)["days"]

    def _day(self, at):
        key = at.strftime("%Y-%m-%d")
        return next((day for day in self._by_day() if day["key"] == key), None)

    def test_each_day_lists_only_what_was_finished_on_it(self):
        self._done("S90001", "Springs", "Spring A", self.today)
        self._done("S90002", "Hardware", "Kit B", self.yesterday)

        day = self._day(self.yesterday)

        self.assertEqual([g["order"] for g in day["groups"]], ["S90002"])
        self.assertEqual(day["count"], 1)

    def test_the_days_run_newest_first(self):
        self._done("S90001", "Springs", "Spring A", self.yesterday)
        self._done("S90002", "Hardware", "Kit B", self.today)

        keys = [day["key"] for day in self._by_day()]

        self.assertEqual(keys, sorted(keys, reverse=True))
        self.assertEqual(keys[0], self.today.strftime("%Y-%m-%d"))

    def test_an_order_finished_over_two_days_shows_on_both(self):
        self._done("S90003", "Tracks", "Track C", self.yesterday)
        self._done("S90003", "Springs", "Spring C", self.today)

        self.assertEqual(self._day(self.today)["orders"], 1)
        self.assertEqual(self._day(self.yesterday)["orders"], 1)

    def test_a_job_still_running_is_not_on_any_day(self):
        self._job("S90004", "Springs", "Spring D", state="progress",
                  logs=[(self.today - timedelta(minutes=10), None)])

        orders = [g["order"] for day in self._by_day() for g in day["groups"]]

        self.assertNotIn("S90004", orders)

    def test_older_days_come_a_page_at_a_time(self):
        self._done("S90005", "Springs", "Spring E", self.today)
        self._done("S90006", "Springs", "Spring F", self.yesterday)

        first = self.env["mrp.workorder"].aa_shop_floor_history_by_day(days=1)

        self.assertEqual(len(first["days"]), 1)
        self.assertTrue(first["more"])
