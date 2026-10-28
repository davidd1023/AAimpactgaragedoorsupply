"""THE PAGE THE STICKER OPENS.

A box goes out with a QR code on it. Somebody - a fitter on a ladder, a driver,
the customer - points a phone at it and gets the door's figures: the spring and
its turns, the drum, the finish, the lift, the cable and the track.

AND SINCE 2026-10-28 IT ALSO DISPATCHES - *"actually the qr code is supposed
to be on the sticker"*. The sticker already had a QR and it already opened
this page, so nothing new is printed on the label: the page simply offers a
Dispatch panel as well, to somebody signed in on the dispatch desk and to
nobody else. One code, two audiences - a second QR on a 1 1/4 inch label
would be two codes a phone has to choose between, and every sticker already
on a shelf would be the wrong one.

THE PANEL IS NOT PUBLIC even though the page is. Reading a door's figures is
harmless; marking an order collected is not, and a public version of that
would let anybody who photographed a box empty the dispatch list. So the
panel is drawn only for `stock.group_stock_user`, and the route that acts
checks again rather than trusting that the button was ever shown.

PUBLIC, AND THE LINK IS THE KEY, which is how the bench screens and the
delivery confirmation already work. The page shows one box and nothing else: no
catalogue, no other orders, no prices, no way to reach the back office and
nothing to post back. The worst a leaked link can do is tell somebody what one
door was built to, which is also the worst the sticker itself can do - it is
printed on the outside of the box.

The token is DERIVED from the database secret rather than stored (see
_aa_box_token), so one box's link says nothing about any other's.
"""

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq

#: Who may dispatch from this page. The page itself stays public - the panel
#: does not.
DISPATCH_GROUP = "stock.group_stock_user"


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

        return request.render("aa_shop_floor.hardware_box_page",
                              self._values(production, card))

    def _values(self, production, card, notice=None, problem=None):
        """The page, plus the dispatch panel for whoever may see it."""
        values = {
            "card": card,
            "company": production.company_id,
            "dispatch": None,
            "notice": notice,
            "problem": problem,
            "production": production,
            "token": production._aa_box_token(),
        }

        if request.env.user.has_group(DISPATCH_GROUP):
            picking = production._aa_dispatch_picking()

            if picking:
                values["dispatch"] = picking._aa_dispatch_scan_state()

        return values

    @http.route("/box/<int:production_id>/<string:token>/dispatch",
                type="http", auth="user", methods=["POST"], website=False,
                sitemap=False)
    def box_dispatch(self, production_id, token, **post):
        """The one tap, from the sticker.

        CHECKED HERE AND NOT ONLY WHERE THE BUTTON WAS DRAWN: the page can
        have been open since this morning, the invoice can have been
        cancelled since, and a form can be posted to directly.
        """
        production = self._production(production_id, token)

        if not production:
            return request.not_found()

        if not request.env.user.has_group(DISPATCH_GROUP):
            return request.not_found()

        card = production._aa_hardware_card()
        picking = production._aa_dispatch_picking()

        if not picking:
            return request.render(
                "aa_shop_floor.hardware_box_page",
                self._values(production, card,
                             problem=_("There is no delivery to dispatch.")))

        state = picking._aa_dispatch_scan_state()

        if state["already"]:
            return request.render(
                "aa_shop_floor.hardware_box_page",
                self._values(production, card,
                             notice=_("Already dispatched.")))

        if not state["paid"]:
            return request.render(
                "aa_shop_floor.hardware_box_page",
                self._values(production, card, problem=state["payment"]))

        if not state["ready"]:
            return request.render(
                "aa_shop_floor.hardware_box_page",
                self._values(production, card,
                             problem=_("That delivery is not ready to go out"
                                       " (%s).", picking.state)))

        try:
            picking.action_aa_dispatched()
        except UserError as error:
            # Odoo's own refusal, in its own words - a lot number it wants,
            # a backorder to decide.
            return request.render(
                "aa_shop_floor.hardware_box_page",
                self._values(production, card, problem=error.args[0]))

        return request.render(
            "aa_shop_floor.hardware_box_page",
            self._values(production, card, notice=_("Dispatched. Thank you.")))
