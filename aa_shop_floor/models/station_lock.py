"""EACH WORKER SEES ONLY HIS OWN STATIONS (owner, 2026-11-26).

"necesito que jorge nada mas q entre a shopfloor su vista sea lo pendiente de
tracks por hacer, el no deve ver mas nada q lo asignado a su mesa lo mismo con
michel deve ver solamente las ordenes asignadas a hw y muelles, el escoge cual
quiere ver hw y le salen las asignadas y muelles y le salen las
correspondientes asignadas"

WHICH STATIONS ARE HIS is already in the database: each work center's
"Allowed Employees" (mrp.workcenter.employee_ids). Track Prep allows Jorge;
Hardware and Springs allow Michel. Nothing new to keep up - give a worker
another station there and he sees it the next time he opens the Shop Floor.

WHO IS LOCKED: a member of `group_shop_floor_only` (the same box that hides
every other app, ir_ui_menu.py) who is not an administrator. Andy, and anybody
without the box, keeps the full Shop Floor with the Overview.

The list travels in the session so the Shop Floor can use it before it draws
anything (station_lock.js): the Shop Floor reads its stations from the browser
synchronously, in setup, so there is no later moment to ask the server.

A worker with the box but no station allowed anywhere gets `False`, which
leaves the Shop Floor as it was rather than showing him an empty screen.
"""

from odoo import models

SHOP_FLOOR_ONLY = "aa_shop_floor.group_shop_floor_only"


class ResUsers(models.Model):
    _inherit = "res.users"

    def _aa_shop_floor_stations(self):
        """[{id, display_name}] of the stations this worker is locked to, or False."""
        self.ensure_one()
        if not self.has_group(SHOP_FLOOR_ONLY) or self.has_group("base.group_system"):
            return False
        employees = self.sudo().employee_ids
        if not employees:
            return False
        stations = self.env["mrp.workcenter"].sudo().search(
            [("employee_ids", "in", employees.ids)], order="sequence, id")
        return [{"id": wc.id, "display_name": wc.display_name} for wc in stations] or False


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        if user and user._is_internal():
            info["aa_shop_floor_stations"] = user._aa_shop_floor_stations()
        return info
