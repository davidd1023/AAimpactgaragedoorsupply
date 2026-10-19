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

    # The sale order the job came from, so the Shop Floor History can show and
    # group every job by order (owner, 2026-10-15).
    aa_sale_order = fields.Char(
        related="production_id.origin", string="Sale Order", store=True, index=True)
    # The number the shop knows the order by (owner, 2026-10-19): W/O #200.
    aa_wo_number = fields.Char(
        related="production_id.aa_wo_number", string="W/O #", store=True, index=True)

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
                "wo": production.aa_wo_number or "",
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

    # ---- One card per sale order in the Overview (owner, 2026-10-14) ----
    # A sale order still makes one manufacturing order per thing to prepare
    # (the track orders consume the RAW track, so they must stay real), but the
    # Overview shows them as ONE card for the order: every job with its own
    # Send / Remove, plus Send all / Remove all.

    aa_order_board = fields.Text(
        string="Order Card (data)", compute="_compute_aa_order_board",
        help="Everything the Overview's one-card-per-order view needs.")

    def _aa_order_siblings(self):
        """The open and finished manufacturing orders of the same sale order."""
        self.ensure_one()
        if not self.origin:
            return self.browse()
        if not self.env["sale.order"].sudo().search_count([("name", "=", self.origin)]):
            return self.browse()
        return self.sudo().search([("origin", "=", self.origin), ("state", "!=", "cancel")], order="id")

    @staticmethod
    def _aa_spec_summary(spec):
        rows = (spec or "").split("\n") if spec else []
        summary, more, items = [], "", 0
        for index, row in enumerate(rows):
            parts = row.split("|")
            if len(parts) < 2 or not parts[1]:
                more = parts[0]
                items = sum(1 for r in rows[index:] if r.split("|")[2:3] == ["c"])
                break
            summary.append([parts[0], parts[1]])
        if more and items:
            more = "%s: %d %s" % (more, items, "item" if items == 1 else "items")
        return summary, more

    @api.depends("origin", "aa_wo_number", "state", "workorder_ids.workcenter_id", "workorder_ids.state",
                 "workorder_ids.duration", "workorder_ids.time_ids.date_end")
    @api.depends_context("uid")
    def _compute_aa_order_board(self):
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        can_assign = self.env.user.has_group(MANAGER_GROUP)
        for production in self:
            siblings = production._aa_order_siblings() if production.id else production.browse()
            if len(siblings) < 2:
                production.aa_order_board = json.dumps({"grouped": False})
                continue
            open_ones = siblings.filtered(lambda p: p.state not in ("done", "cancel"))
            leader = open_ones[:1]
            jobs = []
            for mo in siblings:
                wos = mo.workorder_ids.filtered(lambda w: w.state != "cancel")
                open_wos = wos.filtered(lambda w: w.state != "done")
                waiting = open_wos.filtered(lambda w: w.workcenter_id == pending)
                stations = (open_wos - waiting).workcenter_id
                for wo in waiting:
                    stations |= wo._aa_own_station()
                if not stations:
                    stations = wos.workcenter_id - pending
                if mo.state == "done":
                    status = "done"
                elif not wos:
                    status = "none"
                elif open_wos.filtered(lambda w: w.state == "progress"):
                    status = "progress"
                elif waiting:
                    status = "pending"
                else:
                    status = "station"
                summary, more = self._aa_spec_summary(mo.aa_shop_spec)
                timing = mo._aa_job_timing(wos)
                jobs.append({
                    "id": mo.id,
                    "name": mo.name,
                    "product": mo.product_id.name,
                    "station": ", ".join(stations.mapped("name")),
                    "status": status,
                    "summary": summary,
                    "more": more,
                    "can_send": bool(waiting) and mo.state != "done",
                    "can_remove": bool((open_wos - waiting).filtered(
                        lambda w: w.state not in LOCKED_STATES)),
                    "can_done": mo.state not in ("done", "cancel"),
                    **timing,
                })
            # One section per station (owner, 2026-10-14): vertical and horizontal
            # tracks are one Track Prep task, not two.
            groups = []
            for job in jobs:
                group = next((g for g in groups if g["station"] == job["station"]), None)
                if not group:
                    group = {"id": job["id"], "station": job["station"], "items": [],
                             "send_ids": [], "remove_ids": [], "done_ids": [], "statuses": [],
                             "minutes": 0.0, "running_since": False,
                             "started_utc": False, "finished_utc": False}
                    groups.append(group)
                # Time at the station: closed time plus the clock still running.
                group["minutes"] += job["minutes"]
                for key, pick in (("running_since", min), ("started_utc", min), ("finished_utc", max)):
                    if job[key]:
                        group[key] = pick(group[key], job[key]) if group[key] else job[key]
                group["items"].append({"id": job["id"], "product": job["product"],
                                       "summary": job["summary"], "more": job["more"]})
                group["statuses"].append(job["status"])
                if job["can_send"]:
                    group["send_ids"].append(job["id"])
                if job["can_remove"]:
                    group["remove_ids"].append(job["id"])
                if job["can_done"]:
                    group["done_ids"].append(job["id"])
            for group in groups:
                statuses = set(group.pop("statuses"))
                if statuses == {"done"}:
                    group["status"] = "done"
                elif "progress" in statuses:
                    group["status"] = "progress"
                elif "pending" in statuses:
                    group["status"] = "pending"
                elif statuses <= {"none"}:
                    group["status"] = "none"
                else:
                    group["status"] = "station"
                if group["status"] != "done":
                    group["finished_utc"] = False
                # The card shows these in the tablet's own time zone; the
                # server-side text is only a fallback.
                group["started"] = self._aa_clock(group["started_utc"])
                group["finished"] = self._aa_clock(group["finished_utc"])
            order = self.env["sale.order"].sudo().search([("name", "=", production.origin)], limit=1)
            received = fields.Datetime.context_timestamp(
                production, min(siblings.mapped("create_date"))).strftime("%b %d, %I:%M %p")
            production.aa_order_board = json.dumps({
                "grouped": True,
                "leader": production == leader,
                # The card is headed by the W/O number; the S number only
                # when an order has none (one confirmed before W/O existed).
                "order": production.aa_wo_number or production.origin,
                "customer": order.partner_id.display_name or "",
                "received": received,
                "can_assign": can_assign,
                "send_ids": [j["id"] for j in jobs if j["can_send"]],
                "remove_ids": [j["id"] for j in jobs if j["can_remove"]],
                "jobs": groups,
            })

    # ---- Station timer (owner, 2026-10-15) ----
    # The worker starts the job at the station (Odoo's own work order clock) and
    # Mark as Done stops it. Odoo keeps every start / pause / finish in the work
    # order's time log, which is the history; here the Overview card only reads it.

    def _aa_job_timing(self, workorders):
        """Minutes already logged, when the clock started, when the job ended."""
        logs = workorders.time_ids
        running = logs.filtered(lambda t: not t.date_end)
        started = [d for d in workorders.mapped("date_start") + logs.mapped("date_start") if d]
        finished = [d for d in workorders.mapped("date_finished") if d]
        iso = lambda d: d and fields.Datetime.to_string(d).replace(" ", "T") + "Z"
        return {
            "minutes": sum(workorders.mapped("duration")),
            "running_since": iso(min(running.mapped("date_start"))) if running else False,
            "started_utc": iso(min(started)) if started else False,
            "finished_utc": iso(max(finished)) if finished else False,
        }

    def _aa_clock(self, iso_utc):
        """'2026-10-15T13:05:00Z' -> 'Oct 15, 09:05 AM' in the user's time zone."""
        if not iso_utc:
            return ""
        value = fields.Datetime.to_datetime(iso_utc[:-1].replace("T", " "))
        return fields.Datetime.context_timestamp(self, value).strftime("%b %d, %I:%M %p")

    def aa_mark_done_jobs(self):
        """Manager closes a job from the Overview, sent to its station or still
        pending (owner, 2026-10-14). Same as the station's Mark as Done: the
        work orders finish and the order is produced (a track order consumes
        its RAW and puts the cut track in stock)."""
        self._aa_check_manager()
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        todo = self.filtered(lambda p: p.state not in ("done", "cancel"))
        for production in todo:
            # A pending job goes to its own station first, so the record of who
            # made it and where stays right.
            for wo in production.workorder_ids.filtered(
                    lambda w: w.workcenter_id == pending and w.state not in ("done", "cancel")):
                station = wo._aa_own_station()
                if station and station != pending:
                    wo.workcenter_id = station
            if not production.qty_producing:
                production._set_quantities()
        for production in todo:
            result = production.with_context(
                skip_consumption=True, skip_backorder=True, mo_ids_to_backorder=[],
            ).button_mark_done()
            if production.state != "done":
                raise UserError(_("%s could not be closed from here; open it at its station.",
                                  production.name))
        return True

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
