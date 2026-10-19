"""WHERE THE CUSTOMER'S ORDER HAS GOT TO, on the customer's own page.

The owner, 2026-10-19: in My Account > Your Orders the customer should see the
status of each station - "the tracks for their order is finished, the springs
are currently being worked on, and the hardware has not started yet" - rather
than only Odoo's Not Delivered.

ONE COMPUTATION, THREE READERS. The back office has shown this since the 14th,
under Destination Location on the order's transfer: Pending / Assigned / In
progress / Ready, per station, worked out in stock_picking. That reckoning now
lives here and the picking reads it, so the warehouse and the customer cannot
be told two different things about the same order.

FOUR STATES INSIDE, THREE OUTSIDE. "Pending" and "Assigned" are the difference
between a job that has not been sent to its station and one that is sitting at
it - a real distinction for the manager who does the sending, and none at all
for the customer, who is told what the owner says: not started yet. Nothing
about who is making it, how long it took, or how long it was queued: that is
the shop's business, not the customer's, and a portal page is a public page to
anybody who gets the link.
"""

from odoo import api, models
from odoo.tools.misc import format_date

from .stock_picking import STATION_LABELS

# THE ORDER THE SHOP WORKS IN, so a customer who looks twice sees the same list
# in the same order rather than whatever order the manufacturing orders happen
# to have been created in. Anything not named here follows, alphabetically.
STATION_ORDER = ("Springs", "Tracks", "Hardware", "Cables")

# What each internal status is called on the customer's own page.
CUSTOMER_WORDS = {
    "pending": ("waiting", "Not started"),
    "station": ("waiting", "Not started"),
    "progress": ("making", "Being made"),
    "done": ("done", "Finished"),
}


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    @api.model
    def _aa_station_statuses_for(self, origin):
        """[{station, status, finished}] for one sale order, by its name.

        MOVED HERE FROM stock_picking, unchanged, so that the transfer in the
        back office and the customer's own page read one answer. A station is
        `done` only when every job of the order at that station is done;
        otherwise the worst news wins - something in progress beats something
        merely assigned, because "being made" is the truer answer about the
        station as a whole.
        """
        if not origin:
            return []

        productions = self.sudo().search(
            [("origin", "=", origin), ("state", "!=", "cancel")], order="id")
        pending = self.env["mrp.workcenter"].sudo()._aa_pending()
        groups = {}

        for production in productions:
            workorders = production.workorder_ids.filtered(
                lambda w: w.state != "cancel")

            if not workorders:
                continue

            open_wos = workorders.filtered(lambda w: w.state != "done")
            waiting = open_wos.filtered(lambda w: w.workcenter_id == pending)
            stations = (workorders - waiting).workcenter_id - pending

            for workorder in waiting:
                stations |= workorder._aa_own_station()

            if production.state == "done":
                status = "done"
            elif open_wos.filtered(lambda w: w.state == "progress"):
                status = "progress"
            elif waiting:
                status = "pending"
            else:
                status = "station"

            for name in stations.mapped("name") or ["Shop Floor"]:
                groups.setdefault(name, []).append(
                    (status, production.date_finished))

        result = []

        for name, entries in groups.items():
            found = {status for status, _date in entries}

            if found == {"done"}:
                status = "done"
            elif "progress" in found:
                status = "progress"
            elif "pending" in found:
                status = "pending"
            else:
                status = "station"

            # WHEN IT WAS FINISHED, which is the one thing worth keeping from
            # the block of manufacturing order numbers this replaces on the
            # customer's page. The last of them, because the station is only
            # finished when its last job is.
            dates = [date for done, date in entries if done == "done" and date]
            result.append({
                "station": name,
                "status": status,
                "finished": max(dates) if dates and status == "done" else False,
            })

        return result


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _aa_station_progress(self):
        """What the customer is shown: [{label, state, words}] per station.

        EMPTY WHEN THERE IS NOTHING BEING MADE. An order of stock parts off
        the shelf is not made at a station, and a heading with no stations
        under it would leave a customer wondering what is missing.
        """
        self.ensure_one()
        statuses = self.env["mrp.production"]._aa_station_statuses_for(self.name)
        rows = []

        for entry in statuses:
            state, words = CUSTOMER_WORDS[entry["status"]]
            rows.append({
                "label": STATION_LABELS.get(entry["station"], entry["station"]),
                "state": state,
                "words": words,
                # The day it was finished, in the customer's own date format.
                "date": format_date(self.env, entry["finished"])
                        if entry["finished"] else "",
            })

        def rank(row):
            label = row["label"]

            return (STATION_ORDER.index(label)
                    if label in STATION_ORDER else len(STATION_ORDER), label)

        return sorted(rows, key=rank)

    def _aa_progress_summary(self):
        """"2 of 3 ready", or "" when there is nothing being made."""
        self.ensure_one()
        rows = self._aa_station_progress()

        if not rows:
            return ""

        done = len([row for row in rows if row["state"] == "done"])

        return "%d of %d ready" % (done, len(rows))
