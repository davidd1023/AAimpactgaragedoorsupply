import uuid

from odoo import api, fields, models

# THE THREE BENCHES. Hardware is deliberately not one of them: hinges,
# rollers, drums and shafts are picked off a shelf against the transfer, the
# way they always were. A station is for something somebody BUILDS.
#
# The codes match the sheet's page names, lowercased, because the sheet's
# page rule is what sorts the work - see stock_picking._work_station_sync.
STATIONS = [
    ("springs", "Springs"),
    ("tracks", "Tracks"),
    ("cables", "Cables"),
]


def _token(record=None):
    """A kiosk link's secret. Long enough that it cannot be guessed.

    Takes the record Odoo passes a default callable, and ignores it.
    """
    return uuid.uuid4().hex + uuid.uuid4().hex


class WorkStation(models.Model):
    _name = "work.station"
    _description = "Work station"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Selection(STATIONS, required=True, copy=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # THE LINK IS THE KEY, which is the whole security model here and worth
    # being plain about: anybody holding this URL sees this station's queue and
    # can tick its work off. There is no login, because a bench tablet with a
    # password is a bench tablet nobody logs into. It is long and random, it is
    # never printed on anything that leaves the building, and it can be
    # replaced in one click if a tablet goes missing - which is what
    # action_regenerate_token is for.
    access_token = fields.Char(
        string="Link secret", default=_token, copy=False, required=True,
        groups="stock.group_stock_manager",
    )
    kiosk_url = fields.Char(compute="_compute_kiosk_url", string="Kiosk link")
    item_ids = fields.One2many("work.station.item", "station_id")
    todo_count = fields.Integer(compute="_compute_todo_count", string="To do")

    _code_unique = models.Constraint(
        "UNIQUE(code)", "There is already a station for that kind of work.")

    @api.depends("access_token")
    def _compute_kiosk_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        for station in self:
            station.kiosk_url = "%s/station/%s" % (
                (base or "").rstrip("/"), station.access_token or "")

    def _compute_todo_count(self):
        counts = dict(self.env["work.station.item"]._read_group(
            [("station_id", "in", self.ids), ("state", "=", "todo")],
            groupby=["station_id"], aggregates=["__count"]))

        for station in self:
            station.todo_count = counts.get(station, 0)

    def action_regenerate_token(self):
        """Replace the kiosk link, which immediately kills the old one."""
        for station in self:
            station.access_token = _token()

        return True

    @api.model
    def _station_for_code(self, code):
        """The station that does this kind of work, created if it is missing.

        CREATED ON DEMAND so a database that was upgraded rather than freshly
        installed still sorts work, and so deleting a station by accident
        cannot quietly stop a bench from being fed.
        """
        station = self.sudo().with_context(active_test=False).search(
            [("code", "=", code)], limit=1)

        if station:
            return station

        label = dict(STATIONS).get(code)

        if not label:
            return self.browse()

        return self.sudo().create({"name": label, "code": code})
