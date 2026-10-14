import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# New work orders wait here until the manager picks their station from the
# Shop Floor Overview (owner, 2026-10-14): "las ordenes las quiero asignar yo
# en overview". Workers only see their own station tabs, so a pending order is
# invisible to them until it is assigned.
PENDING_XMLID = "aa_shop_floor.workcenter_pending"
MANAGER_GROUP = "mrp.group_mrp_manager"
LOCKED_STATES = ("progress", "done", "cancel")


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    @api.model
    def _aa_pending(self):
        return self.env.ref(PENDING_XMLID, raise_if_not_found=False) or self.browse()

    @api.model
    def _aa_stations(self):
        """The stations the manager can send work to: every work center but Pending."""
        return self.search([("id", "!=", self._aa_pending().id)], order="sequence, id")


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_suggested_workcenter_id = fields.Many2one(
        "mrp.workcenter", string="Suggested Station", copy=False, readonly=True,
        help="The station this work order's routing points to. The manager decides "
             "where it really goes from the Shop Floor Overview.")

    @api.model_create_multi
    def create(self, vals_list):
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        if pending and not self.env.context.get("aa_keep_workcenter"):
            for vals in vals_list:
                # Only work orders generated from a routing operation. One a worker
                # adds by hand at their own station stays at that station.
                if vals.get("operation_id") and vals.get("workcenter_id") \
                        and vals["workcenter_id"] != pending.id:
                    vals["aa_suggested_workcenter_id"] = vals["workcenter_id"]
                    vals["workcenter_id"] = pending.id
        return super().create(vals_list)

    def aa_assign_workcenter(self, workcenter_id):
        """Send these work orders to a station. Shop Floor managers only."""
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Only a Manufacturing manager can assign work orders to a station."))
        workcenter = self.env["mrp.workcenter"].browse(int(workcenter_id)).exists()
        if not workcenter or workcenter == workcenter._aa_pending():
            raise UserError(_("Pick a station for this work order."))
        locked = self.filtered(lambda wo: wo.state in LOCKED_STATES)
        if locked:
            raise UserError(_("%s is already started or finished; it can't change station.",
                              ", ".join(locked.mapped("name"))))
        self.write({"workcenter_id": workcenter.id})
        return True


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_station_board = fields.Text(
        string="Station Assignment (data)", compute="_compute_aa_station_board",
        help="What the Shop Floor Overview needs to let the manager assign each work order.")

    @api.depends("workorder_ids.workcenter_id", "workorder_ids.state", "create_date")
    @api.depends_context("uid")
    def _compute_aa_station_board(self):
        Workcenter = self.env["mrp.workcenter"].sudo()
        pending = Workcenter._aa_pending()
        can_assign = self.env.user.has_group(MANAGER_GROUP)
        stations = [{"id": wc.id, "name": wc.name} for wc in Workcenter._aa_stations()] \
            if can_assign else []
        for production in self:
            received = ""
            if production.create_date:
                received = fields.Datetime.context_timestamp(
                    production, production.create_date).strftime("%b %d, %I:%M %p")
            wos = [{
                "id": wo.id,
                "name": wo.name,
                "wc": wo.workcenter_id.id,
                "suggested": wo.aa_suggested_workcenter_id.id or False,
                "pending": bool(pending) and wo.workcenter_id == pending,
                "locked": wo.state in LOCKED_STATES,
            } for wo in production.workorder_ids if wo.state != "cancel"]
            production.aa_station_board = json.dumps({
                "can_assign": can_assign,
                "received": received,
                "stations": stations,
                "wos": wos,
            })

    def _split_productions(self, *args, **kwargs):
        # A backorder's work orders stay at the station their order was given.
        return super(MrpProduction, self.with_context(aa_keep_workcenter=True)) \
            ._split_productions(*args, **kwargs)
