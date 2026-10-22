"""TELLING THE SHOP FLOOR THAT SOMETHING CHANGED UNDER IT.

The owner, 2026-10-19: "when i cancel an order in manufacturing it doesnt
automatically cancel it in shop floor".

THE CANCEL ITSELF WAS NEVER THE PROBLEM. Cancelling a manufacturing order
cancels its work orders too - Odoo does that, in every state I could put one
in: confirmed, ready, started. What does not happen is anybody telling the
TABLET. The Shop Floor is a single page that loads its records once and then
only ever reloads when something inside it asks: a button, a dialog closing, a
barcode. It listens to the barcode bus and to nothing else. So a job cancelled
from the Manufacturing app sits on the board until somebody opens the menu and
presses Reload Data - which looks exactly like a cancel that did not work.

SENT TO THE PEOPLE, NOT TO A CHANNEL OF OUR OWN. Odoo warns against sending to
a made-up channel name, because a name somebody can guess is a name somebody
can listen on. Every user is already subscribed to their own channel, so the
notification goes to the shop floor's own users and nowhere else.

WHAT IT CARRIES IS "LOOK AGAIN", nothing more: no record, no state, no reason.
The board re-reads the records it is entitled to and shows whatever is true
now, which is the only answer that cannot go stale.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)

# The browser listens for this and asks the server for its records again.
SHOP_FLOOR_CHANGED = "aa_shop_floor_changed"

# Who is told. The people who might be standing in front of a board, and
# nobody else.
FLOOR_GROUPS = (
    "mrp_workorder.group_mrp_wo_shop_floor",
    "mrp.group_mrp_user",
)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_cancel(self):
        """Cancel the job, then tell every board that is showing it."""
        result = super().action_cancel()
        self._aa_tell_the_shop_floor()

        return result

    def _aa_tell_the_shop_floor(self):
        """"Look again" to whoever may be watching a station.

        NEVER RAISES. A notification is a courtesy; a cancel that went through
        must not be undone because a websocket was unhappy, and the worst case
        without it is the tablet showing a stale card until somebody presses
        Reload Data - which is exactly where this started.
        """
        try:
            partners = self.env["res.partner"]

            for xmlid in FLOOR_GROUPS:
                group = self.env.ref(xmlid, raise_if_not_found=False)

                if group:
                    partners |= group.sudo().user_ids.partner_id

            if partners:
                partners.sudo()._bus_send(SHOP_FLOOR_CHANGED, {})
        except Exception:
            _logger.exception(
                "aa_shop_floor: could not tell the Shop Floor to look again")


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def action_cancel(self):
        """A single job cancelled on its own, rather than its whole order."""
        result = super().action_cancel()
        self.production_id._aa_tell_the_shop_floor()

        return result

    def unlink(self):
        """A bench's job DELETED rather than cancelled.

        The owner, 2026-10-22: "if i delete the work order in manufacturing,
        the assignments in shop floor are still there."

        DELETING A WHOLE ORDER WAS ALREADY COVERED, and by accident rather
        than by design: Odoo's own mrp.production.unlink cancels the order
        before deleting it (mrp/models/mrp_production.py:1130), so the cancel
        hooked above fires and the board hears about it. Deleting a single
        WORK ORDER goes nowhere near a cancel - mrp.workorder.unlink unhooks
        the moves, drops the row and recomputes the order
        (mrp/models/mrp_workorder.py:316) - so nothing told the tablet, and a
        job that no longer existed stayed on the board until somebody pressed
        Reload Data. Which looks exactly like a delete that did not work.

        THE ORDER IS READ BEFORE THE ROW GOES, because afterwards there is no
        row to read it from. It is checked with exists() because these work
        orders may be going as part of their own order being deleted, in which
        case that order is about to follow them.
        """
        productions = self.production_id
        result = super().unlink()
        left = productions.exists()
        self._aa_close_station_jobs_with_nothing_left(left)
        left._aa_tell_the_shop_floor()

        return result

    def _aa_close_station_jobs_with_nothing_left(self, productions):
        """Cancel a station job whose last bench job has just been deleted.

        THE BOARD WAS RIGHT AND THE RECORD WAS WRONG. Telling the tablet to
        look again did not help, because what it looked at was still there:
        deleting the work order leaves the MANUFACTURING ORDER standing, in
        state confirmed, and the Shop Floor shows every order that is not done
        or cancelled. Owner, 2026-10-22: "the work order creates a couple of
        manufacturing order. so maybe even though the work order gets deleted
        the manufacturing order sticks around" - which is exactly it.

        ONLY A STATION JOB, and only one with no bench job left. These are the
        orders this module raises for a spring, a kit or a pair of cables
        (aa_station_kind), and each gets exactly ONE work order, so losing it
        leaves a job with no bench and nothing for anybody to do. An ordinary
        manufacturing order with several operations keeps its own counsel: one
        operation deleted out of four is a change to the route, not the end of
        the job.
        """
        orphans = productions.filtered(
            lambda p: p.aa_station_kind
            and not p.workorder_ids
            and p.state not in ("done", "cancel")
        )

        for job in orphans:
            try:
                with self.env.cr.savepoint():
                    job.sudo().action_cancel()
            except Exception:
                _logger.exception(
                    "aa_shop_floor: %s had its work order deleted and would"
                    " not cancel", job.name)
