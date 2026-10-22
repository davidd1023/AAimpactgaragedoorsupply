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
            "%-16s %-10s %-9s %-9s %s" % (
                _("Job"), _("W/O"), _("State"), _("Order"),
                _("What, and which order")),
        ]
        lines += [job._aa_describe_for_cleanup() for job in jobs]
        lines += ["", _(
            "Jobs whose order was DELETED are deleted with it - there is no"
            " order left to keep a record against. Jobs whose order still"
            " stands and was cancelled are cancelled beside it, so the two"
            " records say the same thing. A job already made is never"
            " touched.")]

        return "\n".join(lines)

    def action_look_again(self):
        self.ensure_one()
        self.report = self._aa_look()

        return self._aa_reopen()

    def action_clear(self):
        """Clear them, matching what happened to the order they were for.

        AN ORDER THAT WAS DELETED LEAVES NOTHING TO KEEP A RECORD AGAINST, so
        its jobs are deleted too - otherwise the Manufacturing list fills with
        cancelled jobs pointing at order numbers that answer to nothing. An
        order that was CANCELLED is still there, so its jobs are cancelled and
        kept beside it.
        """
        self.ensure_one()
        jobs = self.env["mrp.production"]._aa_orphan_station_jobs()
        deleted, cancelled, stuck = [], [], []

        for job in jobs:
            name = job.name
            order_deleted = job._aa_order_fate() == "deleted"

            # ONE THAT WILL NOT GO MUST NOT STOP THE REST. A job that has
            # already consumed something can refuse, and the other eleven
            # should still come off the board.
            try:
                with self.env.cr.savepoint():
                    if order_deleted:
                        job.sudo().unlink()
                        deleted.append(name)
                    else:
                        job.sudo().action_cancel()
                        cancelled.append(name)
            except Exception as error:
                stuck.append("%s (%s)" % (name, error))

        said = [_("Deleted %(deleted)s job(s), cancelled %(cancelled)s.",
                  deleted=len(deleted), cancelled=len(cancelled))]

        if deleted:
            said.append(_("Deleted, with the orders that are gone: %s",
                          ", ".join(deleted)))

        if cancelled:
            said.append(_("Cancelled, beside the orders that still stand: %s",
                          ", ".join(cancelled)))

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
