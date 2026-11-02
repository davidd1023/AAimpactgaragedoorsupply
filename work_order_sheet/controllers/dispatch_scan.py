"""THE PAGE THE DISPATCH QR OPENS.

Owner, 2026-10-28: *"At pickup, the team scans the box sticker with a phone or
tablet. Odoo opens that order, checks every station is done and the invoice is
paid, and marks it Dispatched in one tap."*

**SIGNED IN, UNLIKE THE BOX STICKER.** `/box/...` next door is public because
all it can do is read a door's figures out loud. This route MARKS AN ORDER
COLLECTED, and a public link that did that would let anybody who photographed
a form empty the dispatch list. So: a login, and `stock.group_stock_user` -
the same group that may press the Dispatched button in the back office,
because this IS that button.

The token stays as well. It is not the lock any more, but a URL that is only
an id is a URL somebody edits, and a scanner that silently opens the next
order along is worse than one that refuses.
"""

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

GROUP = "stock.group_stock_user"


class DispatchScan(http.Controller):

    def _picking(self, picking_id, token):
        """The transfer this link is for, or an empty set."""
        picking = request.env["stock.picking"].browse(picking_id).exists()

        if not picking or not picking._aa_dispatch_scan_ok(token):
            return request.env["stock.picking"].browse()

        return picking

    def _page(self, picking, notice=None, problem=None):
        values = picking._aa_dispatch_scan_state()
        values.update({"notice": notice, "problem": problem,
                       "token": picking._aa_dispatch_token()})

        return request.render("work_order_sheet.dispatch_scan_page", values)

    @http.route("/dispatch/<int:picking_id>/<string:token>", type="http",
                auth="user", methods=["GET"], website=True, sitemap=False)
    def dispatch_scan(self, picking_id, token, **kwargs):
        if not request.env.user.has_group(GROUP):
            return request.render("work_order_sheet.dispatch_scan_refused", {})

        picking = self._picking(picking_id, token)

        if not picking:
            return request.not_found()

        return self._page(picking)

    @http.route("/dispatch/<int:picking_id>/<string:token>/go", type="http",
                auth="user", methods=["POST"], website=True, sitemap=False,
                csrf=True)
    def dispatch_go(self, picking_id, token, **post):
        """The one tap.

        CHECKED AGAIN HERE, not only on the page that drew the button. The
        page may have been open since this morning, the invoice may have been
        cancelled since, and a form can be posted to directly - so the bar on
        an unpaid order is applied where it bites rather than where it shows.
        """
        if not request.env.user.has_group(GROUP):
            return request.render("work_order_sheet.dispatch_scan_refused", {})

        picking = self._picking(picking_id, token)

        if not picking:
            return request.not_found()

        state = picking._aa_dispatch_scan_state()

        if state["already"]:
            return self._page(picking, notice=_("Already dispatched."))

        if not state["paid"]:
            return self._page(picking, problem=state["payment"])

        if not state["ready"]:
            return self._page(
                picking,
                problem=_("This transfer is not ready to go out (%s).",
                          picking.state))

        try:
            picking.action_aa_dispatched()
        except UserError as error:
            # ODOO'S OWN REFUSAL, in its own words - a lot number it wants, a
            # backorder to decide. Swallowing it would leave somebody tapping
            # a button that quietly does nothing.
            return self._page(picking, problem=error.args[0])

        return self._page(picking, notice=_("Dispatched. Thank you."))
