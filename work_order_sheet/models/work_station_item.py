from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from .work_station import DISPATCH


class WorkStationItem(models.Model):
    """One thing for one bench to make, for one order.

    A SNAPSHOT, NOT A VIEW. The specification is copied onto the row when the
    work is sorted rather than read back from the order every time the kiosk
    loads. Two reasons, and the first is the important one: a description that
    is edited after the work is sorted must not silently change the spring
    somebody is winding. The second is that the bench tablet then loads a
    table and nothing else - no order, no moves, no parsing.
    """

    _name = "work.station.item"
    _description = "Work station item"
    _order = "order_name, station_id, sequence, id"

    station_id = fields.Many2one(
        "work.station", required=True, ondelete="cascade", index=True)
    picking_id = fields.Many2one(
        "stock.picking", required=True, ondelete="cascade", index=True)
    # The order NUMBER, which is what everyone on the floor calls the job.
    order_name = fields.Char(index=True)
    sequence = fields.Integer(default=10)

    product_id = fields.Many2one("product.product", ondelete="restrict")
    # WRITTEN DOWN, not read through product_id. The sheet already decides what
    # a line is called - the thing bought, not the component that moved - and
    # that is what the bench should read.
    name = fields.Char(required=True)
    code = fields.Char(string="Part number")
    quantity = fields.Float(default=1.0)
    uom_name = fields.Char(string="Unit")

    # What to cut, and what it is for. Both are already worked out for the
    # printed sheet; this is the same text.
    length = fields.Char(string="Cut length")
    door = fields.Char(string="Door")
    detail = fields.Text(string="Specification")

    # IDENTITY ACROSS A RE-SORT. Sorting the same transfer twice must not
    # double the queue, and must not lose what a bench has already ticked off,
    # so each row carries the key it was made from and is matched on it.
    line_key = fields.Char(required=True, index=True)

    # SUPPLIED AS IT COMES, so it reached dispatch complete and no bench ever
    # ticked it off. Kept as a field rather than worked out from the name again
    # at every read: the name on the row is a snapshot, and whether anybody was
    # ever asked to do something to it is a fact about what happened, not a
    # pattern to re-run.
    auto_done = fields.Boolean(string="No work needed", readonly=True)
    auto_done_kind = fields.Char(readonly=True)

    state = fields.Selection(
        [("todo", "To do"), ("done", "Done")],
        default="todo", required=True, index=True)
    done_at = fields.Datetime(string="Finished", readonly=True)
    company_id = fields.Many2one(
        "res.company", related="picking_id.company_id", store=True, index=True)

    _key_unique = models.Constraint(
        "UNIQUE(picking_id, line_key)",
        "That work is already on a station for this transfer.")

    @api.depends("name", "order_name")
    def _compute_display_name(self):
        for item in self:
            item.display_name = "%s - %s" % (item.order_name or "", item.name)

    # --- dispatch cannot go before the benches it waits for --------------

    @api.depends("station_id.code", "picking_id.work_station_ready_to_dispatch",
                 "picking_id.work_station_waiting_for")
    def _compute_is_ready(self):
        """Can this be worked on yet?

        Only dispatch can be too early, and only dispatch has anything to
        wait for: the springs, tracks and cables on the same order.
        """
        for item in self:
            if item.station_id.code != DISPATCH:
                item.is_ready = True
                item.waiting_for = ""
                continue

            item.is_ready = item.picking_id.work_station_ready_to_dispatch
            item.waiting_for = item.picking_id.work_station_waiting_for

    is_ready = fields.Boolean(compute="_compute_is_ready")
    waiting_for = fields.Char(compute="_compute_is_ready")

    def action_done(self):
        """Tick work off, dispatch last.

        THE ORDER OF THE WRITES IS THE RULE. Dispatch is the last thing
        anybody does, so marking a whole order done in one go has to finish
        the making benches first and dispatch after them - otherwise the gate
        below would refuse a dispatch row because of work being ticked off in
        the very same call.

        A dispatch row on its own, with a bench still working, is refused and
        says which bench. That is the rule a kiosk cannot be trusted to keep
        on its own: the Done button is hidden there, and this is what makes
        hiding it true.
        """
        dispatch = self.filtered(lambda i: i.station_id.code == DISPATCH)
        making = self - dispatch
        making._work_station_mark_done()

        blocked = dispatch.filtered(lambda item: not item.is_ready)

        if blocked:
            raise UserError(self.env._(
                "Dispatch is the last step: %(waiting)s still have work on "
                "this order.",
                waiting=blocked[0].waiting_for or self.env._("other stations"),
            ))

        dispatch._work_station_mark_done()

        # TICKING OFF THE LAST BOX DOES NOT SEND THE ORDER OUT. It used to:
        # the transfer validated itself the moment nothing was left to make.
        # The owner asked for a Complete Order button instead, and that is the
        # better rule - a button that fires by itself is not a confirmation of
        # anything, and the last tap on a tablet is a clumsy place to put an
        # irreversible step. See stock_picking._work_station_complete.
        return True

    def _work_station_mark_done(self):
        if self:
            self.write({"state": "done", "done_at": fields.Datetime.now()})
            self._work_station_log(True)

    # --- the order's own log --------------------------------------------------
    #
    # WHEN, NOT JUST WHETHER. The statuses on the work order say where each
    # bench has got to; they cannot say that the springs were finished at
    # 10:42 and the tracks at 14:05. That is a question about a day's work -
    # which order held the floor up, how long a job really took - and the
    # answer belongs in the transfer's own log, where it is kept, dated and
    # attributed without anybody writing it down.
    #
    # AN INTERNAL NOTE, never a message to the customer: mt_note does not mail
    # the followers of the order. A customer does not need to hear that a
    # bench ticked a box.

    def _work_station_log_label(self, item):
        """One line of the log: what was done, as the bench sees it."""
        name = item.name or ""

        if item.quantity and item.quantity != 1:
            name = "%g x %s" % (item.quantity, name)

        if item.length:
            name = "%s (%s)" % (name, item.length)

        return name

    def _work_station_log_auto_done(self):
        """Say in the order's log why nobody will ever tick these off."""
        for picking in self.picking_id:
            items = self.filtered(lambda item: item.picking_id == picking)
            rows = Markup("").join(
                Markup("<li>%s</li>") % self._work_station_log_label(item)
                for item in items
            )
            picking.sudo().message_post(
                body=Markup("<p>%s</p><ul>%s</ul>") % (
                    self.env._(
                        "Complete on arrival at %(station)s - supplied as "
                        "stock, with no work to do:",
                        station=items[0].station_id.name),
                    rows,
                ),
                subtype_xmlid="mail.mt_note")

    def _work_station_log(self, done):
        """Write what just happened into the log of each order it happened to.

        GROUPED BY ORDER AND BENCH, so a bench ticking four things off in one
        go leaves one entry rather than four, and a day's log reads as a
        sequence of events instead of a list of rows.
        """
        for picking in self.picking_id:
            for station in self.filtered(
                    lambda item: item.picking_id == picking).station_id:
                items = self.filtered(
                    lambda item: item.picking_id == picking
                    and item.station_id == station)
                rows = Markup("").join(
                    Markup("<li>%s</li>") % self._work_station_log_label(item)
                    for item in items
                )
                body = Markup("<p><b>%s</b> %s:</p><ul>%s</ul>") % (
                    station.name,
                    self.env._("finished") if done else self.env._("put back"),
                    rows,
                )

                # AND WHETHER THAT WAS THE LAST OF IT, which is the line
                # somebody looking for "when were the springs done" wants.
                if done and picking[dict(picking.WORK_STATION_FIELDS)[
                        station.code]] == "done":
                    body += Markup("<p>%s</p>") % self.env._(
                        "%(station)s has finished every job on this order.",
                        station=station.name)

                picking.sudo().message_post(
                    body=body, subtype_xmlid="mail.mt_note")

    def action_todo(self):
        """Undo, which a bench tablet needs more than a desk does.

        EXCEPT FOR WHAT WAS NEVER DONE. A perforated angle, a shaft or a trim
        arrives complete because there is no work to do to it, so there is
        nothing to put back - the owner's rule, and the kiosk offers no button
        for them either. This is what makes that true rather than merely
        displayed.

        LOGGED LIKE EVERYTHING ELSE. A log that records only the ticking off
        would show work finished that is being done again.
        """
        supplied = self.filtered("auto_done")

        if supplied:
            raise UserError(self.env._(
                "%(name)s needs no work, so there is nothing to put back.",
                name=supplied[0].name,
            ))

        self.write({"state": "todo", "done_at": False})
        self._work_station_log(False)

        return True
