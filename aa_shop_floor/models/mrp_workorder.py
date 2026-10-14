import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# The manager decides which orders the stations work on today (owner,
# 2026-10-14). The station itself never changes - track work is always Track
# Prep, springs always Springs - the manager only puts an order on its station
# or takes it back off. New work orders wait at "Pending Assignment" until the
# manager sends them, so workers only see what was released to them.
PENDING_XMLID = "aa_shop_floor.workcenter_pending"
MANAGER_GROUP = "mrp.group_mrp_manager"
LOCKED_STATES = ("progress", "done", "cancel")


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    @api.model
    def _aa_pending(self):
        return self.env.ref(PENDING_XMLID, raise_if_not_found=False) or self.browse()


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_suggested_workcenter_id = fields.Many2one(
        "mrp.workcenter", string="Own Station", copy=False, readonly=True,
        help="The station this work order belongs to (from its routing). While it "
             "waits at Pending Assignment, this is where the manager will send it.")

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

    def _aa_own_station(self):
        self.ensure_one()
        if self.aa_suggested_workcenter_id:
            return self.aa_suggested_workcenter_id
        return self.operation_id.workcenter_id


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_station_board = fields.Text(
        string="Station Release (data)", compute="_compute_aa_station_board",
        help="What the Shop Floor Overview needs to let the manager send this "
             "order to its station or take it back.")

    @api.depends("workorder_ids.workcenter_id", "workorder_ids.state", "create_date")
    @api.depends_context("uid")
    def _compute_aa_station_board(self):
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        can_assign = self.env.user.has_group(MANAGER_GROUP)
        for production in self:
            received = ""
            if production.create_date:
                received = fields.Datetime.context_timestamp(
                    production, production.create_date).strftime("%b %d, %I:%M %p")
            wos = production.workorder_ids.filtered(lambda wo: wo.state not in ("done", "cancel"))
            waiting = wos.filtered(lambda wo: wo.workcenter_id == pending)
            released = (wos - waiting).filtered(lambda wo: wo.state not in LOCKED_STATES)
            # A loop, not mapped(): mapped() calls the function once on an empty set.
            stations = (wos - waiting).workcenter_id
            for wo in waiting:
                stations |= wo._aa_own_station()
            production.aa_station_board = json.dumps({
                "can_assign": can_assign,
                "received": received,
                "station": ", ".join(stations.mapped("name")),
                "can_send": bool(waiting),
                "can_remove": bool(released),
            })

    def action_confirm(self):
        result = super().action_confirm()
        self._aa_hold_new_workorders()
        return result

    def _aa_hold_new_workorders(self):
        """Every order that just came in waits at Pending Assignment.

        create() already parks most of them, but some flows (the track orders
        made by the stock rules) put the routing's work center back afterwards,
        so this runs once more when the order is confirmed. Nothing here has
        been released by the manager yet, so nothing released is undone.
        """
        if self.env.context.get("aa_keep_workcenter"):
            return
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        if not pending:
            return
        for wo in self.workorder_ids.filtered(lambda w: w.operation_id
                                              and w.workcenter_id != pending
                                              and w.state not in LOCKED_STATES):
            wo.write({
                "aa_suggested_workcenter_id": wo.workcenter_id.id,
                "workcenter_id": pending.id,
            })

    def _aa_check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Only a Manufacturing manager can send orders to the stations."))

    def aa_send_to_station(self):
        """Put the waiting work orders on their own station."""
        self._aa_check_manager()
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        for wo in self.workorder_ids.filtered(lambda w: w.workcenter_id == pending
                                              and w.state not in ("done", "cancel")):
            station = wo._aa_own_station()
            if not station or station == pending:
                raise UserError(_("%s has no station to go to.", wo.display_name))
            wo.workcenter_id = station
        return True

    def aa_remove_from_station(self):
        """Take the not-started work orders back off their station."""
        self._aa_check_manager()
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        if not pending:
            raise UserError(_("The Pending Assignment work center is missing."))
        for wo in self.workorder_ids.filtered(lambda w: w.workcenter_id != pending
                                              and w.state not in LOCKED_STATES):
            wo.write({
                "aa_suggested_workcenter_id": wo.workcenter_id.id,
                "workcenter_id": pending.id,
            })
        return True

    def _split_productions(self, *args, **kwargs):
        # A backorder's work orders stay where their order already is.
        return super(MrpProduction, self.with_context(aa_keep_workcenter=True)) \
            ._split_productions(*args, **kwargs)
