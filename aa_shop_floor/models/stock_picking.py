from markupsafe import Markup, escape

from odoo import fields, models

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
        """[(label, status)] for each station the order's manufacturing orders use."""
        self.ensure_one()
        if not self.origin:
            return []
        productions = self.env["mrp.production"].sudo().search(
            [("origin", "=", self.origin), ("state", "!=", "cancel")], order="id")
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        groups = {}
        for mo in productions:
            wos = mo.workorder_ids.filtered(lambda w: w.state != "cancel")
            if not wos:
                continue
            open_wos = wos.filtered(lambda w: w.state != "done")
            waiting = open_wos.filtered(lambda w: w.workcenter_id == pending)
            stations = (wos - waiting).workcenter_id - pending
            for wo in waiting:
                stations |= wo._aa_own_station()
            if mo.state == "done":
                status = "done"
            elif open_wos.filtered(lambda w: w.state == "progress"):
                status = "progress"
            elif waiting:
                status = "pending"
            else:
                status = "station"
            for name in stations.mapped("name") or ["Shop Floor"]:
                groups.setdefault(name, []).append(status)
        result = []
        for name, statuses in groups.items():
            found = set(statuses)
            if found == {"done"}:
                status = "done"
            elif "progress" in found:
                status = "progress"
            elif "pending" in found:
                status = "pending"
            else:
                status = "station"
            result.append((STATION_LABELS.get(name, name), status))
        return result

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
