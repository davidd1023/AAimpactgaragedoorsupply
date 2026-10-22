"""THE SCREEN THAT CLEARS WORK FOR ORDERS THAT ARE GONE - AND SHOWS ITS WORKING.

The owner, 2026-10-22, after five attempts: "that work for deleted order thing
in manufacturing doesn't work, its like you are not even correctly detecting
the manufacturing orders so nothing is happening."

He is right that nothing can be concluded from a screen that silently does
nothing. So this one lists EVERY unfinished manufacturing order it can see and
says what it intends to do with each - including, and especially, the ones it
is leaving alone and why. If the rule is wrong, the reason column says so; if
his records do not carry what the rule looks for, the columns say that too.

AND IT CAN BE TOLD TO CLEAR THE ONES IT CANNOT ACCOUNT FOR. A job whose order
cannot be found, with nothing on it saying it came from a sale, is not deleted
on a guess - but it is not hidden either, and a tick box clears it. That is his
call to make, not a rule I can write from here.
"""

from odoo import _, api, fields, models

COLUMNS = "%-16s %-10s %-9s %-7s %-8s %-9s %s"


class ShopFloorOrphanCleanup(models.TransientModel):
    _name = "aa.shop.floor.cleanup"
    _description = "Clear Shop Floor work for orders that are gone"

    report = fields.Text(
        string="What is on the board, and what will become of it",
        readonly=True,
        default=lambda self: self._aa_look(),
    )
    job_count = fields.Integer(
        string="Jobs to clear", readonly=True,
        default=lambda self: self._aa_counts()[0])
    unsure_count = fields.Integer(
        string="Jobs that cannot be accounted for", readonly=True,
        default=lambda self: self._aa_counts()[1])
    include_unsure = fields.Boolean(
        string="Also clear the jobs that cannot be accounted for",
        help="Jobs whose order cannot be found and which carry nothing saying"
             " they came from a sale. They may be replenishments or jobs"
             " raised by hand, which is why they are not cleared by default.")

    # --- looking ----------------------------------------------------------

    @api.model
    def _aa_counts(self):
        """(how many will be cleared, how many cannot be accounted for)."""
        survey = self.env["mrp.production"]._aa_cleanup_survey()
        clear = sum(1 for _job, verdict, _why in survey
                    if verdict in ("delete", "cancel"))
        unsure = sum(1 for _job, verdict, _why in survey if verdict == "unsure")

        return clear, unsure

    @api.model
    def _aa_look(self):
        survey = self.env["mrp.production"]._aa_cleanup_survey()

        if not survey:
            return _("There are no unfinished manufacturing orders at all.")

        lines = [
            COLUMNS % (_("Job"), _("W/O"), _("State"), _("Kind"), _("Order"),
                       _("Verdict"), _("Why")),
            "",
        ]

        for job, verdict, why in survey:
            lines.append(COLUMNS % (
                job.name,
                job.aa_wo_number or "-",
                job.state,
                job.aa_station_kind or "-",
                job._aa_order_fate(),
                verdict,
                "%s - %s" % (why, job.product_id.display_name),
            ))

        clear, unsure = self._aa_counts()
        lines += [
            "",
            _("%(clear)s to clear, %(unsure)s that cannot be accounted for,"
              " %(left)s left alone.",
              clear=clear, unsure=unsure,
              left=len(survey) - clear - unsure),
        ]

        if unsure:
            lines.append(_(
                "The ones marked unsure have no order that can be found and"
                " carry nothing saying they came from a sale. Tick the box"
                " below to clear those too."))

        return "\n".join(lines)

    def action_look_again(self):
        self.ensure_one()
        self.report = self._aa_look()
        self.job_count, self.unsure_count = self._aa_counts()

        return self._aa_reopen()

    # --- clearing ---------------------------------------------------------

    def action_clear(self):
        """Clear them, matching what happened to the order they were for.

        An order that was DELETED leaves nothing to keep a record against, so
        its jobs are deleted too. An order that was CANCELLED is still there,
        so its jobs are cancelled and kept beside it.
        """
        self.ensure_one()
        survey = self.env["mrp.production"]._aa_cleanup_survey()
        deleted, cancelled, stuck = [], [], []

        for job, verdict, _why in survey:
            if verdict == "unsure" and self.include_unsure:
                verdict = "delete"

            if verdict not in ("delete", "cancel"):
                continue

            name = job.name

            # ONE THAT WILL NOT GO MUST NOT STOP THE REST.
            try:
                with self.env.cr.savepoint():
                    job.sudo().action_cancel()

                    if verdict == "delete":
                        job.sudo().unlink()
                        deleted.append(name)
                    else:
                        cancelled.append(name)
            except Exception as error:
                stuck.append("%s (%s)" % (name, error))

        said = [_("Deleted %(deleted)s, cancelled %(cancelled)s.",
                  deleted=len(deleted), cancelled=len(cancelled))]

        if deleted:
            said.append(_("Deleted: %s", ", ".join(deleted)))

        if cancelled:
            said.append(_("Cancelled: %s", ", ".join(cancelled)))

        if stuck:
            said += ["", _("These would not go and need closing by hand:")]
            said += stuck

        if not deleted and not cancelled and not stuck:
            said = [_("Nothing was cleared. What the screen can see, and why"
                      " it left each one alone, is above - press Look again"
                      " to re-read it.")]

        self.report = "\n".join(said)
        self.job_count, self.unsure_count = self._aa_counts()
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
