from odoo import fields, http
from odoo.http import request
from odoo.tools import consteq


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
            base + [("state", "=", "done"),
                    ("done_at", ">=", fields.Datetime.start_of(
                        fields.Datetime.now(), "day"))],
            order="done_at desc", limit=12)

        return todo, done

    def _render(self, station, message=""):
        todo, done = self._items(station)

        return request.render("work_order_sheet.station_kiosk", {
            "station": station,
            "todo": todo,
            "done": done,
            "message": message,
            "token": station.access_token,
        })

    @http.route("/station/<string:token>", type="http", auth="public",
                methods=["GET"], website=False, sitemap=False)
    def kiosk(self, token, **kwargs):
        station = self._station(token)

        if not station:
            return request.not_found()

        return self._render(station)

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

        if action == "done":
            item.action_done()
        else:
            item.action_todo()

        # REDIRECTED RATHER THAN RENDERED, so a tablet that reloads does not
        # tick the same job off twice.
        return request.redirect("/station/%s" % station.access_token)
