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

from odoo import api, models

SETTLED = ("done", "cancel")


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _aa_order_is_gone(self):
        """Is the order this job was raised for no longer anywhere?

        THREE WAYS AN ORDER GOES, and this has to recognise all of them: it
        was deleted (the sale line is null and nothing answers to the origin),
        it was cancelled (the line is still there, pointing at a cancelled
        order), or the LINE alone was taken off an order that otherwise
        stands. In every one of them nobody has ordered this any more.
        """
        self.ensure_one()
        line = self.aa_sale_line_id

        if line and line.exists():
            return line.order_id.state == "cancel"

        if self.origin:
            order = self.env["sale.order"].search(
                [("name", "=", self.origin)], limit=1)

            if order:
                return order.state == "cancel"

        return True

    @api.model
    def _aa_orphan_station_jobs(self):
        """Every station job still standing for an order that is not.

        ONLY THIS MODULE'S OWN JOBS (aa_station_kind): the springs, kits and
        cable pairs raised from a sale. A manufacturing order somebody made by
        hand has no sale order behind it and must not be read as abandoned
        because of it.
        """
        jobs = self.search([
            ("aa_station_kind", "!=", False),
            ("state", "not in", SETTLED),
        ])

        return jobs.filtered(lambda job: job._aa_order_is_gone())

    def _aa_describe_for_cleanup(self):
        """One line per job, the way the board names them."""
        self.ensure_one()
        where = self.origin or "-"

        return "%-16s %-10s %-9s %s" % (
            self.name,
            self.aa_wo_number or "-",
            self.state,
            "%s (was %s)" % (self.product_id.display_name, where),
        )
