from markupsafe import Markup, escape

from odoo import api, fields, models

# Under Destination Location on the order's transfer (owner, 2026-10-14): one
# status per thing the order carries - Tracks, Springs, Hardware - and nothing
# for what the order doesn't carry.
STATION_LABELS = {"Track Prep": "Tracks"}
STATUS_BADGES = {
    "pending": ("Pending", "text-bg-warning"),
    "station": ("Assigned", "text-bg-info"),
    "progress": ("In progress", "text-bg-primary"),
    "done": ("Ready", "text-bg-success"),
}


class StockPicking(models.Model):
    _inherit = "stock.picking"

    aa_order_status = fields.Html(
        string="Order Status", compute="_compute_aa_order_status", sanitize=False,
        help="Where each part of the order is in the Shop Floor: Pending (not sent "
             "to its station yet), Assigned (at its station), In progress (being "
             "worked on now) or Ready (finished).")

    def _aa_station_statuses(self):
        """[(label, status)] for each station the order's manufacturing orders use.

        THE RECKONING MOVED TO portal_progress, where the customer's own page
        reads it too. This is the same answer, with the warehouse's own label
        for the Track Prep work center - so the transfer and the customer's
        page cannot say two different things about one order.
        """
        self.ensure_one()

        return [(STATION_LABELS.get(entry["station"], entry["station"]),
                 entry["status"])
                for entry in self.env["mrp.production"]
                ._aa_station_statuses_for(self.origin)]

    def _compute_aa_order_status(self):
        for picking in self:
            statuses = picking._aa_station_statuses() if picking.id else []
            if not statuses:
                picking.aa_order_status = False
                continue
            badges = Markup("").join(
                Markup('<span class="badge rounded-pill %s fs-6 me-2 mb-1">%s: %s</span>') % (
                    STATUS_BADGES[status][1], escape(label), STATUS_BADGES[status][0])
                for label, status in statuses
            )
            picking.aa_order_status = Markup('<div class="d-flex flex-wrap">%s</div>') % badges


    # --- the work sheet being torn down -----------------------------------

    def unlink(self):
        """Deleting a W/O transfer takes that W/O's manufacturing with it.

        THE PATH NONE OF THE OTHER SIX FIXES TOUCHED. The owner's log settled
        it: four jobs on W/O #221, all confirmed, with the Order column
        reading "live". He had deleted the work order and the SALE ORDER was
        still there - so what he deletes is neither the order (hooked) nor
        Odoo's work order (hooked), but the TRANSFER named W/O #221, and
        nothing in this codebase connected that to manufacturing.

        Reproduced before writing this: delete the transfer and the order
        stays `sale`, the job stays `confirmed`, and no transfer is left
        carrying that number. Which is exactly his four rows.

        ONLY WHEN NO TRANSFER IS LEFT FOR THAT W/O. An order can carry
        several - a pick and a delivery - and deleting one of them is not the
        end of the job. When the last one goes there is no sheet left to make
        anything against, so the jobs go too.

        DELETED, NOT CANCELLED, because deleting is what was done to the
        sheet, and because "off the board" is not what he has been asking for
        these six attempts: "i press delete to get rid of them".

        CANCELLING A TRANSFER DOES NOT DO THIS. Odoo cancels transfers of its
        own accord - when an order is cancelled, when a route is replanned -
        and the order's own cancel already takes the work with it. Only an
        outright deletion of the last sheet is read as "this job is off".
        """
        numbers = {
            picking.aa_wo_number for picking in self if picking.aa_wo_number
        }
        result = super().unlink()

        for number in numbers:
            self.env["mrp.production"]._aa_clear_work_for_wo_number(number)

        return result

class StockMove(models.Model):
    _inherit = "stock.move"

    @api.depends("sale_line_id", "bom_line_id")
    def _compute_description_picking(self):
        """A kit's pieces don't repeat the kit's options (owner, 2026-10-14).

        Odoo writes the sale line's options (Plastic Trims, Add to Your Order...)
        on top of every piece of a kit in the Work Order; they belong to the kit,
        not to each hinge and bolt. The "kit - n/total" line stays."""
        super()._compute_description_picking()
        for move in self:
            if not (move.bom_line_id and move.sale_line_id) or move.description_picking_manual:
                continue
            line = move.sale_line_id.with_context(lang=move.sale_line_id.order_id.partner_id.lang)
            options = line._get_sale_order_line_multiline_description_variants().strip()
            text = move.description_picking or ""
            if options and text.startswith(options):
                move.description_picking = text[len(options):].strip()

