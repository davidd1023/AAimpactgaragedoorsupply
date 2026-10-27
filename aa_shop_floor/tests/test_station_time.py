"""STATION TIME: HOW LONG A JOB TAKES, BY WORKER AND BY TASK.

Owner, 2026-10-27: *"average time per task type, per worker, per day. Done
when: you can see how long Michel takes per spring order. (Only visible for
admins)."*

So the test that settles it is literally that: two spring jobs for Michel, one
of 30 minutes and one of 50, and the report saying 40.

The one that matters most after that is the SUMMING. A worker who starts a
spring, breaks for lunch and finishes after leaves THREE entries in Odoo's
time log. Three rows would make the average a third of the truth, so they are
summed back to one row per worker per job before anything is averaged.
"""

from datetime import datetime, timedelta

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class StationTimeCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.michel = self.env["hr.employee"].create({"name": "Michel"})
        self.jorge = self.env["hr.employee"].create({"name": "Jorge"})
        self.product = self.env["product.product"].create({
            "name": "A spring", "type": "consu", "is_storable": True})
        self.workcenter = self.env["mrp.workcenter"].create(
            {"name": "Springs bench"})

        self.productive = self.env["mrp.workcenter.productivity.loss"].search(
            [("loss_id.loss_type", "=", "productive")], limit=1)
        self.blocked = self.env["mrp.workcenter.productivity.loss"].search(
            [("loss_id.loss_type", "!=", "productive")], limit=1)

    # --- fixtures ---------------------------------------------------------

    def _job(self, kind="spring", origin="S00099"):
        production = self.env["mrp.production"].create({
            "product_id": self.product.id, "product_qty": 1.0,
            "origin": origin})
        production.aa_station_kind = kind
        workorder = self.env["mrp.workorder"].create({
            "name": "Wind it", "production_id": production.id,
            "workcenter_id": self.workcenter.id,
            "product_uom_id": self.product.uom_id.id})

        return workorder

    def _clock(self, workorder, employee, minutes, loss=None, day=None,
               finished=True):
        start = day or datetime(2026, 10, 26, 13, 0)

        return self.env["mrp.workcenter.productivity"].create({
            "workorder_id": workorder.id,
            "workcenter_id": self.workcenter.id,
            "employee_id": employee.id,
            "loss_id": (loss or self.productive).id,
            "date_start": start,
            "date_end": start + timedelta(minutes=minutes) if finished else False,
            "duration": minutes,
        })

    def _rows(self, **where):
        domain = [(field, "=", value) for field, value in where.items()]

        return self.env["aa.station.time"].search(domain)

    # --- the sentence he wrote --------------------------------------------

    def test_how_long_michel_takes_per_spring_order(self):
        """THE ONE THAT SETTLES IT. Thirty minutes and fifty is forty."""
        self._clock(self._job(), self.michel, 30)
        self._clock(self._job(), self.michel, 50)

        rows = self._rows(employee_id=self.michel.id, station_kind="spring")

        self.assertEqual(len(rows), 2, "one row per job, not per entry")
        self.assertAlmostEqual(
            sum(rows.mapped("minutes")) / len(rows), 40.0, places=2)

    def test_one_job_in_three_sittings_is_still_one_job(self):
        """A worker who starts, breaks for lunch and finishes leaves three
        entries. Three rows would make the average a third of the truth."""
        job = self._job()
        self._clock(job, self.michel, 10)
        self._clock(job, self.michel, 15)
        self._clock(job, self.michel, 20)

        rows = self._rows(employee_id=self.michel.id, workorder_id=job.id)

        self.assertEqual(len(rows), 1, "the same job counted three times")
        self.assertAlmostEqual(rows.minutes, 45.0, places=2)
        self.assertEqual(rows.jobs, 1)

    def test_two_workers_on_one_job_are_two_rows(self):
        """Michel's time is Michel's and Jorge's is Jorge's, even on the same
        job - which is the whole reason this reads the log and not the work
        order, whose employee_ids is a many-to-many nobody can group by."""
        job = self._job()
        self._clock(job, self.michel, 30)
        self._clock(job, self.jorge, 12)

        self.assertAlmostEqual(
            self._rows(employee_id=self.michel.id).minutes, 30.0, places=2)
        self.assertAlmostEqual(
            self._rows(employee_id=self.jorge.id).minutes, 12.0, places=2)

    # --- what is deliberately left out ------------------------------------

    def test_a_timer_still_running_is_not_counted(self):
        """Its duration is still growing. Averaging it in says a job took
        however far into it somebody happens to be."""
        self._clock(self._job(), self.michel, 7, finished=False)

        self.assertFalse(self._rows(employee_id=self.michel.id))

    def test_blocked_time_is_not_time_michel_took(self):
        """Odoo logs a breakdown against the same work order under another
        loss type. Counting it would be a lie about Michel."""
        if not self.blocked:
            self.skipTest("no non-productive loss reason in this database")

        self._clock(self._job(), self.michel, 90, loss=self.blocked)

        self.assertFalse(self._rows(employee_id=self.michel.id))

    # --- the other two groupings he asked for ------------------------------

    def test_it_separates_the_task_types(self):
        self._clock(self._job(kind="spring"), self.michel, 30)
        self._clock(self._job(kind="kit"), self.michel, 12)

        self.assertAlmostEqual(
            self._rows(employee_id=self.michel.id,
                       station_kind="spring").minutes, 30.0, places=2)
        self.assertAlmostEqual(
            self._rows(employee_id=self.michel.id,
                       station_kind="kit").minutes, 12.0, places=2)

    def test_a_job_with_no_station_kind_is_not_dropped(self):
        """A prepared track job comes from Odoo's own route and carries no
        kind. It is still somebody's time."""
        job = self._job(kind=False)
        self._clock(job, self.michel, 8)

        rows = self._rows(employee_id=self.michel.id)

        self.assertEqual(rows.station_kind, "other")

    def test_it_separates_the_days(self):
        self._clock(self._job(), self.michel, 30,
                    day=datetime(2026, 10, 26, 13, 0))
        self._clock(self._job(), self.michel, 50,
                    day=datetime(2026, 10, 27, 13, 0))

        days = self._rows(employee_id=self.michel.id).mapped("day")

        self.assertEqual(len(set(days)), 2, days)

    def test_the_order_comes_through_so_it_can_be_grouped(self):
        self._clock(self._job(origin="S00123"), self.michel, 30)

        self.assertEqual(self._rows(employee_id=self.michel.id).order_ref,
                         "S00123")

    # --- admins only -------------------------------------------------------

    def test_an_ordinary_employee_cannot_read_it(self):
        """Owner: "Only visible for admins." What people take to do their
        work is not for the people beside them."""
        nosy = self.env["res.users"].create({
            "name": "A fitter", "login": "aa_nosy_fitter",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})

        with self.assertRaises(AccessError):
            self.env["aa.station.time"].with_user(nosy).search([])
