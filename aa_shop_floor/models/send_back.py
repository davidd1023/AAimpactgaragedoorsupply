"""SEND A FINISHED JOB BACK TO ITS STATION (owner, 2026-11-11).

"quiero hacer algo para administrador para que el pueda mandar esas cosas
para atras si se marcaron por confusion y no estan listas" - W/O 942's
hardware had been marked Done from an admin login, with nothing packed.

ODOO CANNOT REOPEN A DONE MANUFACTURING ORDER. Its stock has moved: the job
put what it made on the shelf and took what it used off it. So sending back
is the two things Odoo does offer, in a row:

  1. UNBUILD the finished job, which reverses its stock exactly - what it
     made comes off the shelf, what it used goes back (a spring's coil inches
     to the very lot they came from, a track's RAW piece to the rack);
  2. A FRESH COPY of the job, confirmed and put straight back on the station
     it was finished at - Odoo's own "Duplicate" of a done order.

The old job is marked `aa_sent_back` and drops out of the Overview, the
order's progress and the History, so the order shows ONE job at that station
and it is not done. It is kept rather than hidden from the database: its
chatter says who sent it back and when, which is the record of the mistake.

REFUSED ONCE THE ORDER HAS LEFT. A Work Order already validated has gone to
Dispatch or out of the door; that is a return, not a slip of the finger.

ADMINISTRATORS ONLY, checked here and not only by hiding the button.
"""

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

ADMIN_GROUP = "base.group_system"


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_sent_back = fields.Boolean(
        string="Sent Back to the Station", copy=False, index=True, readonly=True,
        help="This job was marked done by mistake and replaced by a fresh copy; "
             "its stock was reversed by an unbuild.")

    def _aa_send_back_refusal(self):
        """Why this job cannot be sent back, or '' when it can."""
        self.ensure_one()
        if self.state != "done":
            return _("%s is not finished.", self.name)
        if self.aa_sent_back:
            return _("%s was already sent back.", self.name)
        order = self.env["sale.order"].sudo().search([("name", "=", self.origin)], limit=1) \
            if self.origin else self.env["sale.order"]
        if order and hasattr(order, "_aa_work_order_transfers"):
            if order._aa_work_order_transfers().filtered(lambda p: p.state == "done"):
                return _("%(order)s has already gone to Dispatch; sending it back is a return, "
                         "not a correction.", order=order.name)
        return ""

    def aa_send_back(self):
        """Admin: reverse these finished jobs and put a fresh copy of each back
        on the station it was finished at."""
        if not self.env.user.has_group(ADMIN_GROUP):
            raise AccessError(_("Only an administrator can send a finished job back."))
        refusals = [r for r in (p._aa_send_back_refusal() for p in self) if r]
        if refusals:
            raise UserError("\n".join(refusals))
        who = self.env.user.name
        sent = self.env["mrp.production"]
        for old in self.sudo():
            stations = old.workorder_ids.filtered(lambda w: w.state == "done").workcenter_id
            # 1. Reverse the stock exactly.
            unbuild = self.env["mrp.unbuild"].sudo().create({
                "mo_id": old.id,
                "product_id": old.product_id.id,
                "product_qty": old.qty_produced or old.product_qty,
                "product_uom_id": old.product_uom_id.id,
                "bom_id": old.bom_id.id,
                "location_id": old.location_dest_id.id,
                "location_dest_id": old.location_src_id.id,
                "company_id": old.company_id.id,
            })
            try:
                with self.env.cr.savepoint():
                    unbuild.action_unbuild()
            except UserError as error:
                raise UserError(_("%(job)s could not be reversed: %(why)s",
                                  job=old.name, why=error.args[0])) from error
            old.aa_sent_back = True

            # 2. A fresh job, back where it was finished.
            new = old.copy({
                "origin": old.origin,
                "aa_sale_line_id": old.aa_sale_line_id.id,
                "aa_station_kind": old.aa_station_kind,
                "aa_spring_spec_json": old.aa_spring_spec_json,
                "aa_cable_line_ids": [(6, 0, old.aa_cable_line_ids.ids)],
            })
            new.action_confirm()
            pending = self.env["mrp.workcenter"]._aa_pending()
            station = (stations - pending)[:1]
            for wo in new.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel")):
                target = station or wo._aa_own_station()
                if target and target != pending:
                    wo.workcenter_id = target

            note = _("%(who)s sent this back to the station: it had been marked done by "
                     "mistake. Its stock was reversed and %(new)s replaces it.",
                     who=who, new=new.name)
            old.message_post(body=note)
            new.message_post(body=_("%(who)s sent %(old)s back to the station; this job replaces it.",
                                    who=who, old=old.name))
            order = self.env["sale.order"].sudo().search([("name", "=", old.origin)], limit=1)
            if order:
                order.message_post(body=Markup("%s") % escape(note))
            sent |= new
        return sent.ids
