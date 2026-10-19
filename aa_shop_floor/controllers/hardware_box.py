"""THE PAGE THE STICKER OPENS.

A box goes out with a QR code on it. Somebody - a fitter on a ladder, a driver,
the customer - points a phone at it and gets the door's figures: the spring and
its turns, the drum, the finish, the lift, the cable and the track.

PUBLIC, AND THE LINK IS THE KEY, which is how the bench screens and the
delivery confirmation already work. The page shows one box and nothing else: no
catalogue, no other orders, no prices, no way to reach the back office and
nothing to post back. The worst a leaked link can do is tell somebody what one
door was built to, which is also the worst the sticker itself can do - it is
printed on the outside of the box.

The token is DERIVED from the database secret rather than stored (see
_aa_box_token), so one box's link says nothing about any other's.
"""

from odoo import http
from odoo.http import request
from odoo.tools import consteq


class HardwareBox(http.Controller):

    def _production(self, production_id, token):
        """The box this link is for, or an empty set."""
        production = request.env["mrp.production"].sudo().browse(
            production_id).exists()

        if not production or production.aa_station_kind != "kit":
            return request.env["mrp.production"].sudo().browse()

        # Compared in constant time, so the route cannot be turned into a way
        # of measuring how close a guess was.
        if not consteq(token or "", production._aa_box_token()):
            return request.env["mrp.production"].sudo().browse()

        return production

    @http.route("/box/<int:production_id>/<string:token>", type="http",
                auth="public", methods=["GET"], website=False, sitemap=False)
    def box(self, production_id, token, **kwargs):
        production = self._production(production_id, token)

        if not production:
            return request.not_found()

        card = production._aa_hardware_card()

        if not card:
            return request.not_found()

        return request.render("aa_shop_floor.hardware_box_page", {
            "card": card,
            "company": production.company_id,
        })
