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

from odoo import api, fields, models

# HOW FAR BACK THE WHOLE-SHOP VIEW LOOKS. Opening History with no order asks
# "what have we been making", not "everything we have ever made": the last few
# orders answer that, and a tablet should not pull a year of work orders over
# the shop wifi to show twenty of them.
RECENT_ORDERS = 20
RECENT_JOBS_SCANNED = 400


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
        """One finished (or running) job, as the Shop Floor shows it."""
        self.ensure_one()
        production = self.production_id
        product = production.product_id.with_context(display_default_code=False)

        # The clock, and the wall. date_start is when it was first started -
        # Odoo writes it when the first time log opens - and date_finished
        # when it was marked done.
        worked = self.duration or 0.0
        elapsed = 0.0

        if self.date_start and self.date_finished:
            elapsed = (self.date_finished - self.date_start).total_seconds() / 60.0

        return {
            "id": self.id,
            "station": self.workcenter_id.display_name or "",
            "product": product.display_name or "",
            "task": self.name or "",
            "quantity": production.product_qty,
            "uom": production.product_uom_id.name or "",
            "workers": self.employee_ids.mapped("name"),
            "started": self._aa_clock_words(self.date_start),
            "finished": self._aa_clock_words(self.date_finished),
            "worked": self._aa_duration_words(worked),
            # SHOWN ONLY WHEN IT SAYS SOMETHING ELSE. On a job that was done
            # in one sitting the two figures are the same and printing both
            # would be two answers to one question.
            "took": self._aa_duration_words(elapsed)
                    if elapsed and elapsed - worked >= 1 else "",
            "worked_minutes": round(worked, 2),
            "state": self.state,
            "done": self.state == "done",
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
            domain = domain + [("aa_sale_order", "=", order)]
            workorders = self.search(domain, order="id")
        else:
            # Grouped here rather than in SQL because the question is "the
            # last few ORDERS", not the last few jobs, and the window below
            # is bounded either way.
            workorders = self.search(
                domain, order="id desc", limit=RECENT_JOBS_SCANNED)

        groups = []
        by_order = {}

        for workorder in workorders:
            name = workorder.aa_sale_order

            if name not in by_order:
                if not order and len(by_order) >= max(limit, 1):
                    continue

                by_order[name] = {
                    "order": name,
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
            group["customer"] = customers.get(group["order"], "")
            # EVERY PART IN THE ORDER IT WAS MADE IN, oldest first, so the
            # card reads like the order went through the shop.
            group["jobs"].sort(key=lambda job: job["id"])
            group["worked"] = self._aa_duration_words(group["worked_minutes"])
            group["count"] = len(group["jobs"])

        return groups
