"""THE MERGE, WHERE SOMEBODY CAN SEE IT.

The merge runs as a migration, and a migration is invisible: it writes its
report to the build log, which means "did it work?" is answered by reading a
log file on a platform. The first deploy proved why that is not enough - the
catalogue came back unchanged and there was no way to tell, from inside Odoo,
whether the migration had not run or had run and refused every family.

So the same report is a screen. Inventory > Configuration > Catalogue Merge
rehearses all fifteen families - performs them and rolls them back - and shows
what happened, family by family, with the reason underneath any that was left
alone. Nothing is changed by looking.

There is a button to do it for real, which is deliberate. If a migration has
already run and skipped a family that has since been put right - a delivery
validated, a price corrected - the alternative is another deploy to get another
attempt at it.
"""

from odoo import _, api, fields, models


class VariantMergeRehearsal(models.TransientModel):
    _name = "aa.variant.merge.rehearsal"
    _description = "Catalogue merge: rehearsal and report"

    report = fields.Text(
        string="What the merge would do",
        readonly=True,
        default=lambda self: self._aa_run(dry_run=True),
    )
    done = fields.Boolean(
        string="Already merged",
        readonly=True,
        help="True once this screen has merged for real.",
    )

    @api.model
    def _aa_run(self, dry_run=True):
        """The report, as text, from a rehearsal or from the real thing."""
        Template = self.env["product.template"]
        reports = Template._aa_merge_variant_families(dry_run=dry_run)
        heading = (
            _("Rehearsal - nothing was changed:")
            if dry_run
            else _("MERGED FOR REAL:")
        )

        return "%s\n\n%s" % (heading, Template._aa_merge_report(reports))

    def action_rehearse(self):
        """Look again, after something has been put right."""
        self.ensure_one()
        self.report = self._aa_run(dry_run=True)

        return self._aa_reopen()

    def action_merge_for_real(self):
        """Do it. Every family that adds up; the rest left alone and named."""
        self.ensure_one()
        self.report = self._aa_run(dry_run=False)
        self.done = True

        return self._aa_reopen()

    def _aa_reopen(self):
        """Stay on this screen, showing what just happened.

        A wizard that closes on its own would take the report with it, and the
        report is the entire point of the screen.
        """
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
