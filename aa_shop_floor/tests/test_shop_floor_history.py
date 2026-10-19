"""WHAT HAS BEEN MADE, AND HOW LONG IT TOOK.

The owner, 2026-10-19: a history option in the Shop Floor showing all the
finished parts of an order - hardware, springs, tracks - and how long each took
after it was started.

The figures are Odoo's own work order clock, so these tests drive that clock:
they start a job, log time against it, finish it, and read the history back the
way the tablet does.
"""

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class ShopFloorHistoryCase(TransactionCase):

    def setUp(self):
        super().setUp()
        # THE CARD SHOWS THE TABLET'S OWN CLOCK, so a test that asserts a time
        # has to fix the zone or it is really asserting where the server is.
        self.env = self.env(context=dict(self.env.context, tz="UTC"))
        self.partner = self.env["res.partner"].create({"name": "Fitter"})
        self.workcenters = {
            name: self.env["mrp.workcenter"].search(
                [("name", "=ilike", name)], limit=1)
            or self.env["mrp.workcenter"].create({"name": name})
            for name in ("Springs", "Hardware", "Tracks")
        }

    def _product(self, name):
        return self.env["product.product"].create({
            "name": name, "type": "consu", "is_storable": True})

    def _job(self, order, station, product_name, minutes=None, logs=(),
             started=None, finished=None, state="done"):
        """A manufacturing order with one work order, as the stations make them.

        `logs` are turns at the bench, (start, end), which is what the Shop
        Floor really writes and what `duration` is computed from. `started`
        and `finished` are the PLANNED window - what Odoo schedules and what
        it shows in date_start / date_finished until the job is really
        finished.

        WRITING `minutes` IS NOT THE SAME AS CLOCKING THEM, and that caught me
        out: mrp.workorder.duration has an inverse, so writing it makes Odoo
        fabricate a time log of that length starting NOW. Tests about the
        words a duration is said in may use it; tests about WHEN something
        happened must use `logs`.
        """
        product = self._product(product_name)
        production = self.env["mrp.production"].create({
            "product_id": product.id,
            "product_qty": 1.0,
            "origin": order,
        })
        values = {
            "name": "Make it",
            "production_id": production.id,
            "product_uom_id": production.product_uom_id.id,
            "workcenter_id": self.workcenters[station].id,
            "state": state,
            "date_start": started,
            "date_finished": finished,
        }

        if minutes is not None:
            values["duration"] = minutes

        workorder = self.env["mrp.workorder"].create(values)

        for log_start, log_end in logs:
            self._log(workorder, log_start, log_end)

        workorder.invalidate_recordset()

        return production, workorder

    def _log(self, workorder, start, end=None):
        """A turn at the bench: Start opens one of these, Mark as Done closes
        it. This is the clock `duration` is summed from."""
        return self.env["mrp.workcenter.productivity"].create({
            "workorder_id": workorder.id,
            "workcenter_id": workorder.workcenter_id.id,
            "date_start": start,
            "date_end": end,
            "loss_id": self.env.ref("mrp.block_reason7").id,
        })

    def _history(self, order=None):
        return self.env["mrp.workorder"].aa_shop_floor_history(order=order)

    # --- every part of the order ---------------------------------------------

    def test_the_order_s_finished_parts_are_all_there(self):
        """"the hardware, springs, and tracks" - every station's job, under
        the one order, in the order the shop made them."""
        self._job("S00123", "Springs", "Custom Torsion Spring Assembly")
        self._job("S00123", "Hardware", "AA-1200 Hardware Kit")
        self._job("S00123", "Tracks", '3" Vertical Track 76"')
        history = self._history("S00123")

        self.assertEqual(len(history), 1, "one card per order")
        group = history[0]
        self.assertEqual(group["order"], "S00123")
        self.assertEqual(group["count"], 3)
        self.assertEqual(group["done"], 3)
        self.assertEqual([job["station"] for job in group["jobs"]],
                         ["Springs", "Hardware", "Tracks"])
        self.assertIn("Spring", group["jobs"][0]["product"])

    def test_the_customer_is_named(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        self._job(order.name, "Hardware", "AA-1200 Hardware Kit")
        self.assertEqual(self._history(order.name)[0]["customer"], "Fitter")

    def test_another_order_s_parts_stay_on_that_order(self):
        self._job("S00123", "Springs", "A spring")
        self._job("S00124", "Springs", "Another spring")
        self.assertEqual(self._history("S00123")[0]["count"], 1)
        self.assertEqual(
            self._history("S00123")[0]["jobs"][0]["product"], "A spring")

    def test_a_job_nobody_has_started_is_not_history(self):
        """It is the board, not the history. A list that showed it would
        answer "what has been made" with things that have not been."""
        self._job("S00123", "Springs", "Not started", state="ready")
        self._job("S00123", "Hardware", "Started", state="progress")
        group = self._history("S00123")[0]
        self.assertEqual(group["count"], 1)
        self.assertEqual(group["jobs"][0]["product"], "Started")
        self.assertEqual(group["done"], 0, "started is not finished")

    def test_a_job_with_no_sale_order_is_left_out(self):
        """A manufacturing order raised in the back office belongs to no
        order, so it has no order card to appear on."""
        self._job(False, "Springs", "Stock spring")
        self.assertFalse([group for group in self._history()
                          if any(job["product"] == "Stock spring"
                                 for job in group["jobs"])])

    # --- how long each took --------------------------------------------------

    def test_how_long_it_took_after_starting(self):
        start = datetime(2026, 10, 19, 13, 0, 0)
        self._job("S00123", "Springs", "A spring",
                  logs=[(start, start + timedelta(minutes=12))])
        job = self._history("S00123")[0]["jobs"][0]
        self.assertEqual(job["worked"], "12 min")
        self.assertEqual(job["worked_minutes"], 12.0)
        self.assertEqual(job["started"], "Oct 19, 01:00 PM")
        self.assertEqual(job["finished"], "Oct 19, 01:12 PM")

    def test_an_hour_is_said_as_an_hour(self):
        self._job("S00123", "Hardware", "A kit", minutes=65.0)
        self.assertEqual(self._history("S00123")[0]["jobs"][0]["worked"],
                         "1 h 05 min")

    def test_a_job_that_sat_on_the_bench_says_both_figures(self):
        """TWO HONEST ANSWERS. Forty minutes of work spread over a day is not
        a forty minute job and not a seven hour one.

        Two turns at the bench, which is what a paused and resumed job is."""
        self._job("S00123", "Hardware", "A kit", logs=[
            (datetime(2026, 10, 19, 9, 0, 0), datetime(2026, 10, 19, 9, 20, 0)),
            (datetime(2026, 10, 19, 15, 40, 0), datetime(2026, 10, 19, 16, 0, 0)),
        ])
        job = self._history("S00123")[0]["jobs"][0]
        self.assertEqual(job["worked"], "40 min")
        self.assertEqual(job["took"], "7 h 00 min")
        self.assertEqual(job["started"], "Oct 19, 09:00 AM")
        self.assertEqual(job["finished"], "Oct 19, 04:00 PM")

    def test_a_job_done_in_one_sitting_says_one_figure(self):
        """The wall and the clock agree, so printing both would be two
        answers to one question."""
        start = datetime(2026, 10, 19, 9, 0, 0)
        self._job("S00123", "Springs", "A spring",
                  logs=[(start, start + timedelta(minutes=30))])
        self.assertFalse(self._history("S00123")[0]["jobs"][0]["took"])

    def test_the_order_s_total_is_the_sum_of_its_parts(self):
        self._job("S00123", "Springs", "A spring", minutes=10.0)
        self._job("S00123", "Hardware", "A kit", minutes=20.5)
        self._job("S00123", "Tracks", "A track", minutes=29.5)
        group = self._history("S00123")[0]
        self.assertEqual(group["worked_minutes"], 60.0)
        self.assertEqual(group["worked"], "1 h 00 min")

    def test_a_job_with_no_time_on_it_says_nothing_about_time(self):
        """Marked done without the clock ever running - which the manager's
        own Mark as Done does from the Overview. A zero would read like a job
        that took no time instead of one nobody timed."""
        self._job("S00123", "Springs", "A spring", minutes=0.0)
        self.assertEqual(self._history("S00123")[0]["jobs"][0]["worked"], "")

    def test_half_a_minute_rounds_up(self):
        """Python's own round() is banker's rounding: it makes 18.5 minutes
        18 and 74.5 minutes 74. Defensible arithmetic, wrong time sheet."""
        self._job("S00123", "Hardware", "A kit", minutes=18.5)
        self._job("S00123", "Springs", "A spring", minutes=56.0)
        group = self._history("S00123")[0]
        self.assertEqual(
            [job["worked"] for job in group["jobs"]], ["19 min", "56 min"])
        self.assertEqual(group["worked"], "1 h 15 min")

    def test_seconds_are_not_dressed_up_as_minutes(self):
        self._job("S00123", "Springs", "A spring", minutes=0.4)
        self.assertEqual(self._history("S00123")[0]["jobs"][0]["worked"],
                         "under a minute")

    # --- the whole shop, not one order ---------------------------------------

    def test_the_whole_shop_shows_the_newest_orders_first(self):
        """Opening History with no order asks "what have we been making"."""
        for name in ("S00001", "S00002", "S00003"):
            self._job(name, "Springs", "A spring %s" % name)

        history = self._history()
        names = [group["order"] for group in history]
        self.assertEqual(names[:3], ["S00003", "S00002", "S00001"])

    def test_the_whole_shop_view_is_bounded(self):
        """A tablet should not pull a year of work orders over the shop wifi
        to show twenty of them."""
        for index in range(25):
            self._job("S%05d" % index, "Springs", "A spring")

        self.assertLessEqual(len(self._history()), 20)

    def test_one_order_s_history_is_not_bounded_by_that(self):
        """The limit is on how many ORDERS the whole-shop view shows, not on
        how many parts an order may have."""
        for index in range(25):
            self._job("S00123", "Springs", "Spring %d" % index)

        self.assertEqual(self._history("S00123")[0]["count"], 25)

    # --- the same figures as the Reporting list ------------------------------

    def test_it_reads_the_same_jobs_as_the_reporting_list(self):
        """ONE SOURCE. The Shop Floor History list in Manufacturing >
        Reporting and this dialog answer the same question, so they use the
        same domain rather than two that can drift apart."""
        action = self.env.ref("aa_shop_floor.aa_shop_floor_history_action")
        workorder = self.env["mrp.workorder"]
        self.assertEqual(
            [term for term in workorder._aa_history_domain()
             if term[0] == "state"],
            [term for term in eval(action.domain) if term[0] == "state"])


@tagged("post_install", "-at_install")
class RunningJobCase(ShopFloorHistoryCase):
    """THE BUG THE OWNER CAUGHT, 2026-10-19.

    A job still running read "2 h 00 min start to finish" and "Oct 19, 08:55
    AM -> Oct 19, 10:55 AM", for a finish that had not happened. date_start
    and date_finished on a work order are a computed PLANNED window: starting
    the job overwrites the start with the real time and leaves the finish as
    the plan - the start plus the expected duration - so reading it as an
    actual finish made every running job look like it had finished exactly on
    schedule, two hours being the expected duration rather than anything that
    happened.
    """

    def _running(self, expected=120.0):
        """A job started at 08:55 and not finished, planned to take two hours
        - exactly the case in the owner's screenshot.

        No duration is written: the clock is an OPEN log, which is what Start
        leaves behind and what Mark as Done would close.
        """
        start = datetime(2026, 10, 19, 8, 55, 0)
        _production, workorder = self._job(
            "S00040", "Hardware", "AA-1200 Hardware Kit",
            started=start, finished=start + timedelta(minutes=expected),
            state="progress")
        self._log(workorder, start)
        workorder.invalidate_recordset()

        return workorder

    def test_a_running_job_has_no_finish(self):
        self._running()
        job = self._history("S00040")[0]["jobs"][0]
        self.assertFalse(job["finished"], "it has not finished")
        self.assertFalse(job["took"], "there is no finish to measure to")
        self.assertTrue(job["running"])
        self.assertFalse(job["done"])

    def test_a_running_job_says_when_it_was_started(self):
        self._running()
        job = self._history("S00040")[0]["jobs"][0]
        self.assertIn("08:55 AM", job["started"])

    def test_the_planned_window_is_never_shown_as_time_taken(self):
        """Two hours was the EXPECTED duration. Nothing on the card may
        present it as something that happened."""
        self._running(expected=120.0)
        job = self._history("S00040")[0]["jobs"][0]
        self.assertNotIn("2 h", job["took"] or "")
        self.assertNotIn("10:55", job["finished"] or "")

    def test_finishing_it_gives_the_real_times(self):
        workorder = self._running()
        # Mark as Done: the log closes and the job finishes. The duration
        # follows from the log rather than being written over it.
        workorder.time_ids[:1].date_end = datetime(2026, 10, 19, 9, 35, 0)
        workorder.write({"state": "done",
                         "date_finished": datetime(2026, 10, 19, 9, 35, 0)})
        workorder.invalidate_recordset()
        job = self._history("S00040")[0]["jobs"][0]
        self.assertIn("09:35 AM", job["finished"])
        self.assertEqual(job["worked"], "40 min")
        self.assertFalse(job["took"], "it was done in one sitting")
        self.assertTrue(job["done"])

    def test_a_job_put_down_is_paused_rather_than_running(self):
        """Started and set aside: the clock is not ticking and the job is not
        finished, and a board somebody reads to find out what is happening
        should not call that Running."""
        workorder = self._running()
        workorder.time_ids.date_end = datetime(2026, 10, 19, 9, 5, 0)
        job = self._history("S00040")[0]["jobs"][0]
        self.assertFalse(job["running"])
        self.assertFalse(job["done"])
        self.assertFalse(job["finished"], "paused is not finished")

    def test_the_real_start_wins_over_the_planned_one(self):
        """A job planned for the morning and started in the afternoon is said
        to have started in the afternoon."""
        start = datetime(2026, 10, 19, 14, 20, 0)
        _production, workorder = self._job(
            "S00041", "Springs", "A spring",
            started=datetime(2026, 10, 19, 8, 0, 0),
            finished=datetime(2026, 10, 19, 9, 0, 0), state="progress")
        self._log(workorder, start)
        workorder.invalidate_recordset()
        self.assertIn("02:20 PM", self._history("S00041")[0]["jobs"][0]["started"])
