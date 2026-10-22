"""WHAT HAS BEEN MADE, AND HOW LONG IT TOOK - inside the Shop Floor.

The owner, 2026-10-19: a history option in the Shop Floor showing all the
finished parts of an order - the hardware, the springs, the tracks - and how
long each took after it was started.

THE FIGURES ARE ODOO'S OWN. A worker taps Start and the work order's clock
runs; Mark as Done stops it. Odoo keeps every start, pause and finish in the
work order's time log and adds the minutes up in `duration`, which is what the
Shop Floor History list in Manufacturing > Reporting has shown since the 15th.
Nothing new is recorded here and no second tally is kept - this is the same
figures, read where the work happens, because a tablet bolted to a bench
cannot reach the back office's Reporting menu.

TWO DIFFERENT HONEST ANSWERS to "how long did it take", and the difference
between them is worth seeing:

  * WORKED is the clock - the minutes somebody was actually on it.
  * TOOK is the wall, start to finish - which includes the hour it sat on the
    bench while they did something else, and the night in between.

A job started at 9 and marked done at 4 with twenty minutes on the clock is not
a seven-hour job, and it is not a twenty-minute job either. Both are shown, and
TOOK only when it says something WORKED does not.
"""

from datetime import timedelta

from odoo import api, fields, models

# HOW FAR BACK THE WHOLE-SHOP VIEW LOOKS. Opening History with no order asks
# "what have we been making", not "everything we have ever made": the last few
# orders answer that, and a tablet should not pull a year of work orders over
# the shop wifi to show twenty of them.
RECENT_ORDERS = 20
RECENT_JOBS_SCANNED = 400

# BY DAY (owner, 2026-10-21: "everything that was done in one day, the orders
# separated by the day they were finished"). How many days back the day list
# reaches, and the most finished jobs it reads to build it - a bound, so the
# tablet never pulls the whole year over the shop wifi.
DAYS_BACK = 60
DAY_JOBS_SCANNED = 3000
# Days shown at first; "Show older days" adds this many more each time.
DAYS_SHOWN = 7


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # --- what to call a job and how long it took ------------------------------

    @api.model
    def _aa_duration_words(self, minutes):
        """12.0 -> "12 min"; 65.4 -> "1 h 05 min"; 0.4 -> "under a minute"."""
        minutes = float(minutes or 0)

        if minutes <= 0:
            return ""

        if minutes < 1:
            return "under a minute"

        # HALF A MINUTE ROUNDS UP, which is what anybody reading a stopwatch
        # expects. Python's own round() is banker's rounding and turns 18.5
        # into 18 and 74.5 into 74 - defensible arithmetic, and the wrong
        # answer on a time sheet.
        whole = int(minutes + 0.5)

        if whole < 60:
            return "%d min" % whole

        return "%d h %02d min" % divmod(whole, 60)

    def _aa_history_job(self):
        """One finished (or running) job, as the Shop Floor shows it.

        THE CLOCK IS THE TIME LOG, NOT THE SCHEDULE, and getting that wrong
        is what the owner caught on 2026-10-19: a job still running said
        "2 h 00 min start to finish" and "Oct 19, 08:55 AM -> Oct 19, 10:55
        AM" for a finish that had not happened.

        `date_start` and `date_finished` on a work order are a COMPUTED
        PLANNED WINDOW - core even calls them the planned dates when it
        refuses an end before a start. Starting a job overwrites date_start
        with the real time, and finishing it overwrites date_finished; until
        then date_finished is still the plan, which is the start plus the
        expected duration. Reading it as an actual finish turns every running
        job into a job that finished exactly on schedule.

        So the times come from mrp.workcenter.productivity - the log Start and
        Mark as Done write, the same log `duration` is summed from - and a
        finish is only shown when there is one.
        """
        self.ensure_one()
        production = self.production_id
        product = production.product_id.with_context(display_default_code=False)

        logs = self.time_ids
        log_starts = [log.date_start for log in logs if log.date_start]
        log_ends = [log.date_end for log in logs if log.date_end]
        # The clock is ticking when a log has been opened and not closed.
        running = any(not log.date_end for log in logs)
        done = self.state == "done"

        started = min(log_starts) if log_starts else False

        if not started and self.state == "progress":
            # Started, but the log is not written yet.
            started = self.date_start

        finished = False

        if done and not running:
            # A done job's own date_finished IS the real one - finishing is
            # what writes it - and it is the only answer for a job the manager
            # marked done from the Overview without the clock ever running.
            finished = max(log_ends) if log_ends else self.date_finished

        worked = self.duration or 0.0
        elapsed = 0.0

        if started and finished:
            elapsed = (finished - started).total_seconds() / 60.0

        return {
            "id": self.id,
            "station": self.workcenter_id.display_name or "",
            "product": product.display_name or "",
            "task": self.name or "",
            "quantity": production.product_qty,
            "uom": production.product_uom_id.name or "",
            "workers": self.employee_ids.mapped("name"),
            "started": self._aa_clock_words(started),
            "finished": self._aa_clock_words(finished),
            "worked": self._aa_duration_words(worked),
            # SHOWN ONLY WHEN IT SAYS SOMETHING ELSE. On a job that was done
            # in one sitting the two figures are the same and printing both
            # would be two answers to one question.
            "took": self._aa_duration_words(elapsed)
                    if elapsed and elapsed - worked >= 1 else "",
            "worked_minutes": round(worked, 2),
            "state": self.state,
            "done": done,
            # RUNNING AND PAUSED ARE NOT THE SAME THING on a board somebody
            # is reading to find out what is happening: one has somebody on
            # it, the other was started and put down.
            "running": running,
        }

    def _aa_clock_words(self, value):
        """A stored (UTC) datetime as the tablet's own clock reads it."""
        if not value:
            return ""

        return fields.Datetime.context_timestamp(self, value).strftime(
            "%b %d, %I:%M %p")

    # --- the history itself ---------------------------------------------------

    @api.model
    def _aa_history_domain(self):
        """Every job that has actually been started, and nothing else.

        THE SAME DOMAIN THE REPORTING LIST USES, so the two cannot disagree.
        A job still waiting at a station is not history - it is the board.
        """
        return [("state", "in", ("progress", "done")),
                ("aa_sale_order", "!=", False)]

    @api.model
    def aa_shop_floor_history(self, order=None, limit=RECENT_ORDERS):
        """[{order, jobs: [...]}] - the finished parts of an order, in order.

        Called with an `order` (a sale order name) for one order's history,
        which is what the order card asks for; called with none for the last
        few orders, which is what the Shop Floor's own History menu asks for.
        """
        domain = self._aa_history_domain()

        if order:
            # The order card now names its order by W/O # (owner,
            # 2026-10-19); an S number still finds it too.
            domain = domain + ["|", ("aa_sale_order", "=", order),
                               ("aa_wo_number", "=", order)]
            workorders = self.search(domain, order="id")
        else:
            # Grouped here rather than in SQL because the question is "the
            # last few ORDERS", not the last few jobs, and the window below
            # is bounded either way.
            workorders = self.search(
                domain, order="id desc", limit=RECENT_JOBS_SCANNED)

        return workorders._aa_history_groups(
            order_limit=None if order else max(limit, 1))

    def _aa_history_groups(self, order_limit=None):
        """These jobs as the History shows them: one group per order, in the
        order the orders first appear here, each with its jobs oldest first.
        `order_limit` stops at that many orders."""
        groups = []
        by_order = {}

        for workorder in self:
            name = workorder.aa_sale_order

            if name not in by_order:
                if order_limit and len(by_order) >= order_limit:
                    continue

                by_order[name] = {
                    "order": workorder.aa_wo_number or name,
                    "sale": name,
                    "customer": "",
                    "jobs": [],
                    "worked_minutes": 0.0,
                    "done": 0,
                }
                groups.append(by_order[name])

            group = by_order[name]
            job = workorder._aa_history_job()
            group["jobs"].append(job)
            group["worked_minutes"] += job["worked_minutes"]
            group["done"] += 1 if job["done"] else 0

        sale_orders = self.env["sale.order"].sudo().search(
            [("name", "in", list(by_order))])
        customers = {so.name: so.partner_id.display_name or "" for so in sale_orders}

        for group in groups:
            group["customer"] = customers.get(group.pop("sale"), "")
            # EVERY PART IN THE ORDER IT WAS MADE IN, oldest first, so the
            # card reads like the order went through the shop.
            group["jobs"].sort(key=lambda job: job["id"])
            group["worked"] = self._aa_duration_words(group["worked_minutes"])
            group["count"] = len(group["jobs"])

        return groups

    # --- by day ---------------------------------------------------------------
    #
    # A JOB BELONGS TO THE DAY IT WAS FINISHED, on the shop's own calendar -
    # the tablet's time zone, not UTC, or everything marked done after 8 PM
    # would land on tomorrow. Only finished jobs: a day's list is what that
    # day produced, and a job still running has produced nothing yet.

    def _aa_finished_at(self):
        """When this job was really finished (see _aa_history_job)."""
        self.ensure_one()
        ends = [log.date_end for log in self.time_ids if log.date_end]
        return max(ends) if ends else self.date_finished

    @api.model
    def aa_shop_floor_history_by_day(self, days=DAYS_SHOWN):
        """[{key, label, orders, count, worked, groups}] - the History
        organised by the day things were finished, newest day first.

        NOT A DAY TO PICK (owner, 2026-10-21: "not choose - organised by
        day"): every day is shown, one under the other, each with the orders
        whose parts were finished that day. `days` is how many days with work
        in them to return; the dialog asks for more as it is scrolled back.
        Returns {days: [...], more: bool}.
        """
        since = fields.Datetime.now() - timedelta(days=DAYS_BACK + 1)
        workorders = self.search(
            [("state", "=", "done"), ("aa_sale_order", "!=", False),
             ("date_finished", ">=", since)],
            order="date_finished desc, id desc", limit=DAY_JOBS_SCANNED)

        by_day = {}

        for workorder in workorders:
            finished = workorder._aa_finished_at()

            if not finished:
                continue

            local = fields.Datetime.context_timestamp(workorder, finished)
            key = local.strftime("%Y-%m-%d")
            entry = by_day.setdefault(key, {
                "key": key,
                "label": local.strftime("%A, %b %d"),
                "workorders": self.browse(),
            })
            entry["workorders"] |= workorder

        ordered = sorted(by_day.values(), key=lambda entry: entry["key"], reverse=True)
        wanted = max(int(days or DAYS_SHOWN), 1)
        result = []

        for entry in ordered[:wanted]:
            # Oldest first within the day, so it reads in the order it was worked.
            groups = entry["workorders"].sorted("id")._aa_history_groups()
            minutes = sum(group["worked_minutes"] for group in groups)
            result.append({
                "key": entry["key"],
                "label": entry["label"],
                "orders": len(groups),
                "count": len(entry["workorders"]),
                "worked": self._aa_duration_words(minutes),
                "groups": groups,
            })

        return {"days": result, "more": len(ordered) > wanted}
