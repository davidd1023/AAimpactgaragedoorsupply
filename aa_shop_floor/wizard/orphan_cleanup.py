"""THE SCREEN THAT CLEARS WORK FOR ORDERS THAT ARE GONE.

Deliberate, and it shows its working first. The owner deleted an order and its
two jobs stayed on the board; a hook fixes that from now on, and this is for
every one already standing - which no hook can ever reach, because the order
they belonged to is not there to be cancelled again.
"""

from odoo import _, api, fields, models


class ShopFloorOrphanCleanup(models.TransientModel):
    _name = "aa.shop.floor.cleanup"
    _description = "Clear Shop Floor work for orders that are gone"

    report = fields.Text(
        string="Work with no order behind it",
        readonly=True,
        default=lambda self: self._aa_look(),
    )
    job_count = fields.Integer(readonly=True, default=lambda self: len(
        self.env["mrp.production"]._aa_orphan_station_jobs()))

    @api.model
    def _aa_look(self):
        """What is standing, as text. Changes nothing."""
        jobs = self.env["mrp.production"]._aa_orphan_station_jobs()

        if not jobs:
            return _("Nothing on the board is for an order that is gone.")

        lines = [
            _("%s job(s) for orders that have been deleted or cancelled:",
              len(jobs)),
            "",
            "%-16s %-10s %-9s %s" % (
                _("Job"), _("W/O"), _("State"), _("What, and which order")),
        ]
        lines += [job._aa_describe_for_cleanup() for job in jobs]
        lines += ["", _(
            "Cancelling these takes them off the Shop Floor. Nothing is"
            " deleted: a cancelled job is still a record of what was asked"
            " for.")]

        return "\n".join(lines)

    def action_look_again(self):
        self.ensure_one()
        self.report = self._aa_look()

        return self._aa_reopen()

    def action_clear(self):
        """Cancel them, one at a time, and say what happened."""
        self.ensure_one()
        jobs = self.env["mrp.production"]._aa_orphan_station_jobs()
        done, stuck = [], []

        for job in jobs:
            # ONE THAT WILL NOT CANCEL MUST NOT STOP THE REST. A job that has
            # already consumed something can refuse, and the other eleven
            # should still come off the board.
            try:
                with self.env.cr.savepoint():
                    job.sudo().action_cancel()
                done.append(job.name)
            except Exception as error:
                stuck.append("%s (%s)" % (job.name, error))

        said = [_("Cancelled %s job(s).", len(done))]

        if done:
            said.append(", ".join(done))

        if stuck:
            said += ["", _("These would not cancel and need closing by hand:")]
            said += stuck

        self.report = "\n".join(said)
        self.job_count = len(
            self.env["mrp.production"]._aa_orphan_station_jobs())

        # And the boards showing them are told to look again.
        self.env["mrp.production"]._aa_tell_the_shop_floor()

        return self._aa_reopen()

    def _aa_reopen(self):
        """Stay here, showing what just happened."""
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
