from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq

from ..models.work_station import DISPATCH


class WorkStationKiosk(http.Controller):
    """The bench tablet.

    PUBLIC, AND THE LINK IS THE KEY. The owner chose a kiosk link over a login
    per station, which is the right trade for a tablet bolted to a bench and
    the wrong one for anything carrying a price, so this serves exactly one
    thing: the queue for the station the link names. Nothing here takes a
    station from the request - not a parameter, not a session, not a referer -
    so a link cannot be edited into another bench's work. That is the whole
    rule, and the tests exist to prove it stays true.
    """

    def _station(self, token):
        """The station this link belongs to, or none.

        COMPARED IN CONSTANT TIME. A plain == on a secret leaks how much of a
        guess was right to anybody who can time the response; consteq is what
        Odoo uses for its own access tokens, for the same reason.
        """
        token = (token or "").strip()

        if len(token) < 32:
            return request.env["work.station"].sudo().browse()

        for station in request.env["work.station"].sudo().search([]):
            if station.access_token and consteq(station.access_token, token):
                return station

        return request.env["work.station"].sudo().browse()

    def _items(self, station):
        """What is waiting at this bench, and what it just finished."""
        Item = request.env["work.station.item"].sudo()
        base = [
            ("station_id", "=", station.id),
            ("picking_id.state", "not in", ("done", "cancel")),
        ]
        todo = Item.search(base + [("state", "=", "todo")])
        # A SHORT TAIL OF FINISHED WORK, so a mis-tap can be undone. Only
        # today's, and only a few: this is an undo button, not a history.
        done = Item.search(
            base + [("state", "=", "done"), ("auto_done", "=", False),
                    ("done_at", ">=", fields.Datetime.start_of(
                        fields.Datetime.now(), "day"))],
            order="done_at desc", limit=12)
        # AND WHAT NEEDED NOTHING. Shown, because the dispatcher should see
        # that the trims are part of this order and that nothing is expected
        # of them - an order that is ready to send with no sign of half its
        # contents invites somebody to go looking. Never with a button: there
        # is no work to undo.
        supplied = Item.search(
            base + [("auto_done", "=", True)], order="order_name, id")

        return todo, done, supplied

    def _ready_orders(self, station):
        """Orders whose work is all made and which dispatch can now send out.

        DISPATCH ONLY. Every station can finish its own work; only the last one
        says the order is finished, so no other kiosk is offered the button -
        and the route checks the same thing, since a page is not a permission.

        ANY FINISHED ORDER, NOT ONLY ONE DISPATCH HAD A ROW ON. This asked for
        dispatch's own items first, which meant an order of nothing but tracks
        - cut, ticked off, finished - never appeared here and could not be
        completed by anybody on the floor at all. Dispatch is the step that
        SENDS AN ORDER OUT; having nothing to gather for it does not make it
        somebody else's to close.

        An order with no station work of any kind is still none of its
        business, which is what keeps every unrelated transfer in the
        warehouse off this screen.
        """
        if station.code != DISPATCH:
            return request.env["stock.picking"].sudo().browse()

        return request.env["stock.picking"].sudo().search([
            ("state", "not in", ("done", "cancel")),
            ("work_station_item_ids", "!=", False),
            ("work_station_todo_count", "=", 0),
        ], order="id")

    def _render(self, station, message=""):
        todo, done, supplied = self._items(station)

        return request.render("work_order_sheet.station_kiosk", {
            "station": station,
            "todo": todo,
            "done": done,
            "supplied": supplied,
            "ready": self._ready_orders(station),
            "message": message,
            "token": station.access_token,
        })

    @http.route("/station/<string:token>", type="http", auth="public",
                methods=["GET"], website=False, sitemap=False)
    def kiosk(self, token, completed=None, **kwargs):
        station = self._station(token)

        if not station:
            return request.not_found()

        # SAID ONCE, AFTER A REDIRECT. The order that was just sent out has
        # left this screen by the time it reloads, so without this the only
        # sign that the button worked is a row disappearing. The id is looked
        # up rather than the name echoed back, so nothing a visitor types
        # reaches the page.
        message = ""

        if completed and str(completed).isdigit():
            picking = request.env["stock.picking"].sudo().browse(
                int(completed)).exists()

            if picking and picking.state == "done":
                message = request.env._(
                    "Order %(name)s is complete and on its way.",
                    name=picking.origin or picking.name)

        return self._render(station, message=message)

    @http.route("/station/<string:token>/complete/<int:picking_id>",
                type="http", auth="public", methods=["POST"], website=False,
                sitemap=False, csrf=False)
    def complete(self, token, picking_id, **kwargs):
        """The final confirmation: dispatch says the order is finished.

        CHECKED THREE WAYS, because this one closes an order rather than
        ticking off a row: the link has to be dispatch's, the order has to be
        one dispatch actually has work on, and every station on it has to be
        done. The model enforces the last of those whatever the page shows.
        """
        station = self._station(token)

        if not station or station.code != DISPATCH:
            return request.not_found()

        picking = request.env["stock.picking"].sudo().browse(picking_id).exists()

        if not picking or picking not in self._ready_orders(station):
            return request.not_found()

        try:
            reason = picking._work_station_complete()
        except UserError as error:
            return self._render(station, message=str(error))

        if reason:
            return self._render(station, message=request.env._(
                "The work is recorded, but this order needs the office to "
                "finish it: %(reason)s", reason=reason))

        return request.redirect(
            "/station/%s?completed=%s" % (station.access_token, picking.id))

    @http.route("/station/<string:token>/<string:action>/<int:item_id>",
                type="http", auth="public", methods=["POST"], website=False,
                sitemap=False, csrf=False)
    def mark(self, token, action, item_id, **kwargs):
        """Tick a job off, or put it back.

        THE ITEM IS CHECKED AGAINST THE LINK, not merely looked up. Posting
        another station's item id to this URL has to do nothing, or the
        separation between benches would be a matter of what the page happens
        to show.
        """
        station = self._station(token)

        if not station or action not in ("done", "todo"):
            return request.not_found()

        item = request.env["work.station.item"].sudo().browse(item_id).exists()

        if not item or item.station_id != station:
            return request.not_found()

        try:
            if action == "todo":
                item.action_todo()

                return request.redirect("/station/%s" % station.access_token)

            item.action_done()
        except UserError as error:
            # DISPATCH TOO EARLY, almost certainly: the model refuses it and
            # says which bench is still working. A bench tablet must never show
            # a traceback, so the reason is shown as a line at the top of its
            # own page.
            return self._render(station, message=str(error))

        # REDIRECTED RATHER THAN RENDERED, so a tablet that reloads does not
        # tick the same job off twice.
        return request.redirect("/station/%s" % station.access_token)
