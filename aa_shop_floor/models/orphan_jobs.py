"""WORK LEFT BEHIND BY AN ORDER THAT IS NO LONGER THERE.

The owner, 2026-10-22, with a photograph of his own board: W/O #213 showing
AAM/MO/00086 "Pack hardware kit" and AAM/MO/00087 "Cut coil, install cones",
for an order he had deleted.

WHY THE LAST FIX DID NOT REACH THESE. Cancelling an order now stops its jobs,
and deleting an order means cancelling it first - Odoo refuses to delete a
confirmed one - so from here on the board clears itself. But a hook only ever
fires at the moment somebody presses something. Every job orphaned BEFORE that
existed is still standing, and nothing that runs on a cancel can ever reach
them: their order is gone, their sale line was set to null when it went, and
all that is left is an `origin` naming a sale order that cannot be found.

So they have to be swept up deliberately, and looked at first - which is what
the screen in wizard/orphan_cleanup.py is for. Nothing here cancels anything by
itself: a job somebody is part way through is still somebody's afternoon.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

SETTLED = ("done", "cancel")


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _aa_order_fate(self):
        """What became of the order this job was raised for.

        "live"      - somebody is still waiting for it; leave it alone.
        "cancelled" - the order is there and cancelled; cancel the job beside
                      it, so the two records say the same thing.
        "deleted"   - there is no order any more: the sale line was set to
                      null when it went and nothing answers to the origin.
                      Nothing is left to keep a record against, so the job
                      goes too.

        THE THIRD CASE IS THE ONE THAT NEEDED SAYING. A job cancelled beside a
        cancelled order is a pair that makes sense. A job cancelled beside an
        order NUMBER that answers to nothing is litter in the Manufacturing
        list, which is what the owner was looking at when he said "the
        manufacturing orders are still there".
        """
        self.ensure_one()
        line = self.aa_sale_line_id

        if line and line.exists():
            return "cancelled" if line.order_id.state == "cancel" else "live"

        if self.origin:
            order = self.env["sale.order"].search(
                [("name", "=", self.origin)], limit=1)

            if order:
                return "cancelled" if order.state == "cancel" else "live"

        return "deleted"

    def _aa_is_this_shops_work(self):
        """Was this job raised by one of this shop's orders?

        THREE MARKS, AND THE THIRD IS THE ONE THAT WAS MISSING. A station kind
        or a sale line says so outright, and both are written by
        _aa_create_station_productions. But the PREPARED TRACK jobs come from
        Odoo's own route rather than from that code, so they carry neither -
        and they were being left as "cannot be accounted for" even while
        showing W/O #220 in their own column.

        A W/O number is proof enough. It is computed from the origin and
        STORED, so it survives the order it came from being deleted, which is
        exactly when it is needed: by then the sale line is null and nothing
        answers to the origin, and that number is all that is left to say
        whose work this was. Owner, 2026-10-22, with a photograph of four such
        jobs: "i deleted their work order but they are still there."
        """
        self.ensure_one()

        return bool(
            self.aa_station_kind
            or self.aa_sale_line_id.exists()
            or self.aa_wo_number
        )

    def _aa_cleanup_verdict(self):
        """(verdict, reason) - what should become of this job, and why.

        SAID OUT LOUD FOR EVERY JOB, including the ones nothing happens to,
        because "nothing is happening" is exactly what the owner saw five
        times running and neither of us could tell whether the rule was wrong
        or the records simply did not match it (2026-10-22: "its like you are
        not even correctly detecting the manufacturing orders").

        "delete"   - its order was deleted and this job came from a sale.
        "cancel"   - its order is there and cancelled; cancel this beside it.
        "unsure"   - its order cannot be found AND nothing on the job says it
                     came from a sale at all. It may be a replenishment, or a
                     job somebody raised by hand. Not deleted on a guess - it
                     is listed, and clearing it is a separate, ticked choice.
        "leave"    - with the reason, which is the line worth reading when the
                     screen appears to do nothing.
        """
        self.ensure_one()

        if self.state == "done":
            return "leave", "already made"

        if any(w.state == "done" for w in self.workorder_ids):
            return "leave", "work has been done on it"

        # A CANCELLED JOB IS LITTER, WHATEVER ITS ORDER IS DOING. This is the
        # case the owner kept coming back about: seven rows reading cancel,
        # left alone because their orders were still live, and still sitting
        # in his Manufacturing list. Nobody is going to make a cancelled job -
        # it is not work, and it is not a record of work. If the kit is wanted
        # after all, the order raises a new job for it.
        #
        # Ours to clear means ours to have raised: a station job, or anything
        # carrying one of this shop's W/O numbers - which is how the prepared
        # track jobs Odoo's own route puts up are recognised, since they have
        # no station kind but do belong to an order.
        if self.state == "cancel":
            if self._aa_is_this_shops_work():
                return "delete", "cancelled, so nothing is going to be made"

            return "leave", "cancelled, but not a job this shop raised"

        fate = self._aa_order_fate()

        if fate == "live":
            return "leave", "its order is still live"

        if fate == "cancelled":
            return "cancel", "its order was cancelled"

        # The order is gone. Is this job ours - raised from a sale?
        if self._aa_is_this_shops_work():
            return "delete", "its order was deleted"

        if not self.origin:
            return "unsure", "it names no order at all, and nothing on it" \
                " says it came from a sale"

        return "unsure", "no order answers to %s, and nothing on it says it" \
            " came from a sale" % self.origin

    @api.model
    def _aa_cleanup_survey(self, limit=300):
        """Every job that is not finished, with what will become of it.

        The point is the ones that are LEFT ALONE: this is the screen that has
        to be able to say why nothing happened.
        """
        jobs = self.search([("state", "!=", "done")], order="id desc",
                           limit=limit)

        return [(job, ) + job._aa_cleanup_verdict() for job in jobs]

    @api.model
    def _aa_orphan_station_jobs(self):
        """Every station job whose order is cancelled or gone.

        ONLY THIS MODULE'S OWN JOBS (aa_station_kind): the springs, kits and
        cable pairs raised from a sale. A manufacturing order somebody made by
        hand has no sale order behind it and must not be read as abandoned
        because of it.

        A JOB ALREADY CANCELLED IS INCLUDED WHEN ITS ORDER WAS DELETED, and
        only then. It is off the Shop Floor already, but it is still a row in
        the Manufacturing list naming an order that cannot be opened, and
        there is nothing left for it to be a record of. A job already DONE is
        never here: it was made, and that happened whatever became of the
        paperwork.
        """
        jobs = self.search([
            ("aa_station_kind", "!=", False),
            ("state", "!=", "done"),
        ])

        return jobs.filtered(
            lambda job: job._aa_order_fate() == "deleted"
            or (job.state != "cancel" and job._aa_order_fate() == "cancelled")
        )

    def _aa_delete_station_jobs(self):
        """Delete these jobs outright, one at a time, keeping what refuses.

        DELETING IS WHAT MATCHES A DELETED ORDER. Odoo deletes a manufacturing
        order by cancelling it first and taking its work orders with it
        (mrp/models/mrp_production.py:1130), and refuses outright for one that
        is already done - which is the right refusal: a job that was made is a
        record of something that happened, whatever became of the paperwork.

        ONE AT A TIME, IN ITS OWN SAVEPOINT, because an order being deleted
        must not be held up by a job that will not go. What will not go is
        left behind rather than taking the delete down with it.
        """
        gone = self.browse()

        for job in self:
            try:
                with self.env.cr.savepoint():
                    job.sudo().unlink()
                gone |= job
            except Exception:
                _logger.exception(
                    "aa_shop_floor: %s would not delete with its order",
                    job.name)

        return gone

    def _aa_describe_for_cleanup(self):
        """One line per job, the way the board names them."""
        self.ensure_one()
        where = self.origin or "-"

        return "%-16s %-10s %-9s %-9s %s" % (
            self.name,
            self.aa_wo_number or "-",
            self.state,
            self._aa_order_fate(),
            "%s (was %s)" % (self.product_id.display_name, where),
        )
