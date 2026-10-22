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
