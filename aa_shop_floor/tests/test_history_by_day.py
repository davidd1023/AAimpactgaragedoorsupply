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

    def _by_day(self, day=None):
        return self.env["mrp.workorder"].aa_shop_floor_history_by_day(day=day)

    def test_each_day_lists_only_what_was_finished_on_it(self):
        self._done("S90001", "Springs", "Spring A", self.today)
        self._done("S90002", "Hardware", "Kit B", self.yesterday)

        result = self._by_day(self.yesterday.strftime("%Y-%m-%d"))

        self.assertEqual([g["order"] for g in result["groups"]], ["S90002"])
        self.assertEqual(result["count"], 1)

    def test_the_newest_day_opens_first(self):
        self._done("S90001", "Springs", "Spring A", self.today)
        self._done("S90002", "Hardware", "Kit B", self.yesterday)

        result = self._by_day()
        keys = [day["key"] for day in result["days"]]

        self.assertEqual(result["day"], self.today.strftime("%Y-%m-%d"))
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_an_order_finished_over_two_days_shows_on_both(self):
        self._done("S90003", "Tracks", "Track C", self.yesterday)
        self._done("S90003", "Springs", "Spring C", self.today)

        days = {day["key"]: day for day in self._by_day()["days"]}

        self.assertEqual(days[self.today.strftime("%Y-%m-%d")]["orders"], 1)
        self.assertEqual(days[self.yesterday.strftime("%Y-%m-%d")]["orders"], 1)

    def test_a_job_still_running_is_not_on_any_day(self):
        _production, workorder = self._job(
            "S90004", "Springs", "Spring D", state="progress",
            logs=[(self.today - timedelta(minutes=10), None)])

        groups = self._by_day(self.today.strftime("%Y-%m-%d"))["groups"]

        self.assertNotIn("S90004", [g["order"] for g in groups])
