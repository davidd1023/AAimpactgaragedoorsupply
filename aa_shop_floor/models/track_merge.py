"""ONE TRACK TASK PER ORDER AT THE STATION (owner, 2026-11-02).

"cada vez que mando un track a jorge me salen dos tareas por separadas para la
misma orden, una para el vertical y otra para el horizontal, juntame las dos"

The Overview already showed them as one Track Prep task (2026-10-14). At the
station they were still two cards, because they ARE two manufacturing orders:
each consumes its own RAW track, so they stay separate in the books.

What changes is only what Jorge sees and presses:

  * the open Track Prep work orders of one sale order become ONE card, carried
    by the lowest work order; the others are hidden and their instructions are
    drawn inside the carrier's card (``aa_track_merge``);
  * when the carrier is finished - Mark as Done on its own work order, or the
    production closed straight away - the hidden ones are finished with it, the
    same way a manager's Mark as Done on the Overview closes a job.

The clock runs on the carrier only. Starting both would count every minute
twice in the station's time.
"""

import json

from odoo import api, fields, models

# The stations where an order's jobs are one card. Only Track Prep: the
# Hardware card is a packing list per box with its own sticker.
MERGE_STATIONS = ("Track Prep",)
CLOSED = ("done", "cancel")


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_track_merge = fields.Text(
        string="Merged Station Card (data)", compute="_compute_aa_track_merge",
        help="Whether this job is drawn on another job's card at its station, "
             "and the instructions of the jobs drawn on this one.")

    def _aa_merge_group(self):
        """The open jobs of the same sale order at the same merging station,
        lowest first (the first is the carrier)."""
        self.ensure_one()
        if (self.state in CLOSED or not self.aa_sale_order
                or self.workcenter_id.name not in MERGE_STATIONS):
            return self.browse()
        return self.sudo().search([
            ("aa_sale_order", "=", self.aa_sale_order),
            ("workcenter_id", "=", self.workcenter_id.id),
            ("state", "not in", CLOSED),
            ("production_id.state", "not in", CLOSED),
        ], order="id")

    @api.depends("state", "workcenter_id", "aa_sale_order", "production_id.state")
    def _compute_aa_track_merge(self):
        for wo in self:
            group = wo._aa_merge_group() if wo.id else wo.browse()
            if len(group) < 2:
                wo.aa_track_merge = json.dumps({"hidden": False, "partners": []})
                continue
            carrier = group[0]
            partners = []
            if wo == carrier:
                # ONE ENTRY PER TRACK, not per step: a vertical is three work
                # orders (cut, flag angle, jamb brackets) of one production,
                # and its cut list is the production's. The carrier's own
                # production is already drawn by the card itself.
                seen = carrier.production_id
                for other in group[1:]:
                    production = other.production_id
                    if production in seen:
                        continue
                    seen |= production
                    partners.append({
                        "id": other.id,
                        "production_id": production.id,
                        "product": production.product_id.display_name,
                        "spec": production.aa_shop_spec or "",
                        "packed": production.aa_packed or "[]",
                    })
            wo.aa_track_merge = json.dumps({"hidden": wo != carrier, "partners": partners})

    def _aa_merge_partners(self):
        """The hidden jobs this carrier stands for."""
        partners = self.browse()
        for wo in self:
            group = wo._aa_merge_group_any_state()
            if group and group[0] == wo:
                partners |= group[1:]
        return partners

    def _aa_merge_group_any_state(self):
        """The group as it was before this job finished: the job itself (open
        or just done) plus the still-open jobs beside it."""
        self.ensure_one()
        if not self.aa_sale_order or self.workcenter_id.name not in MERGE_STATIONS:
            return self.browse()
        others = self.sudo().search([
            ("aa_sale_order", "=", self.aa_sale_order),
            ("workcenter_id", "=", self.workcenter_id.id),
            ("state", "not in", CLOSED),
            ("production_id.state", "not in", CLOSED),
            ("id", "!=", self.id),
        ], order="id")
        if not others or others[0].id < self.id:
            # Not the carrier: a lower job is still open and carries the card.
            return self.browse()
        return self.sudo() | others

    def do_finish(self):
        if self.env.context.get("aa_merging"):
            return super().do_finish()
        # Read the partners BEFORE finishing: afterwards this job is done and no
        # longer looks like the carrier of anything.
        partners = self._aa_merge_partners()
        result = super().do_finish()
        if partners:
            partners.production_id._aa_close_merged_jobs()
        return result


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _aa_close_merged_jobs(self):
        """Finish hidden jobs the way the Overview's Mark as Done does: the
        work orders finish and the order is produced (the RAW is consumed)."""
        todo = self.sudo().filtered(lambda p: p.state not in CLOSED)
        for production in todo:
            if not production.qty_producing:
                production._set_quantities()
        for production in todo:
            if production.state in CLOSED:
                continue
            production.with_context(
                aa_merging=True, skip_consumption=True, skip_backorder=True,
                mo_ids_to_backorder=[],
            ).button_mark_done()

    def button_mark_done(self):
        if self.env.context.get("aa_merging"):
            return super().button_mark_done()
        # The Shop Floor closes a production straight from its last work order
        # when the operation type closes automatically, without do_finish.
        partners = self.workorder_ids.filtered(
            lambda w: w.state not in CLOSED)._aa_merge_partners()
        result = super().button_mark_done()
        partners = partners.filtered(
            lambda w: w.production_id.state not in CLOSED
            and w.production_id not in self)
        if partners and any(p.state == "done" for p in self):
            partners.production_id._aa_close_merged_jobs()
        return result
