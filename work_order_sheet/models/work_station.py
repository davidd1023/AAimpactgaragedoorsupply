import uuid

from odoo import api, fields, models

# THE BENCHES, IN THE ORDER THE WORK GOES THROUGH THEM.
#
# Three make something - springs, tracks, cables - and the last one, Hardware,
# gathers what is left and sends the order out, so it cannot start until the
# other three have finished. That order is the sequence here, and it
# is also a rule the code enforces rather than a hope about how people work:
# see work_station_item.action_done.
#
# The sheet's own page rule is what sorts the work, so each station is the
# page that feeds it - and Hardware feeds Dispatch, which is the one place the
# two names differ. The page is what a part IS; the station is who handles it.
STATIONS = [
    ("springs", "Springs"),
    ("tracks", "Tracks"),
    ("cables", "Cables"),
    # CALLED HARDWARE, and the code stays "dispatch". The word is what the
    # bench is called - the owner renamed it - and the code is what the
    # software calls the last step; renaming a stored value to follow a label
    # buys nothing and breaks every row that points at it.
    ("dispatch", "Hardware"),
]

# The station that finishes an order, and the ones it waits for.
DISPATCH = "dispatch"
MAKERS = ("springs", "tracks", "cables")


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
    # KEPT FROM ORDINARY USERS, and from both kinds of administrator it is not.
    # A Manufacturing administrator runs the floor and must be able to replace
    # a link; mrp.group_mrp_manager implies only stock.group_stock_user, so
    # naming the Inventory group alone locked out exactly the right person.
    #
    # The computed link carries the same groups as the secret inside it, or it
    # would hand the secret to anybody who can read the station.
    SECRET_GROUPS = "stock.group_stock_manager,mrp.group_mrp_manager"

    access_token = fields.Char(
        string="Link secret", default=_token, copy=False, required=True,
        groups=SECRET_GROUPS,
    )
    kiosk_url = fields.Char(
        compute="_compute_kiosk_url", string="Kiosk link",
        groups=SECRET_GROUPS)
    item_ids = fields.One2many("work.station.item", "station_id")
    todo_count = fields.Integer(compute="_compute_todo_count", string="To do")

    _code_unique = models.Constraint(
        "UNIQUE(code)", "There is already a station for that kind of work.")

    @api.depends("access_token")
    def _compute_kiosk_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        for station in self:
            # SUDO FOR ITS OWN READ. Whoever is allowed to read kiosk_url is
            # allowed to read the token - they are the same groups - but the
            # compute also runs on behalf of whatever triggered it, and a
            # recompute that raises on a field this very method is building
            # would be a strange way to fail.
            station.kiosk_url = "%s/station/%s" % (
                (base or "").rstrip("/"), station.sudo().access_token or "")

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
    def _station_label(self, code):
        """What this station is CALLED, which the owner may have changed.

        A bench renamed on the live site should be named that way in the line
        telling dispatch who it is waiting for, so the record is asked first
        and the shipped label is only the fallback.
        """
        station = self.sudo().with_context(active_test=False).search(
            [("code", "=", code)], limit=1)

        return station.name or dict(STATIONS).get(code, code)

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
