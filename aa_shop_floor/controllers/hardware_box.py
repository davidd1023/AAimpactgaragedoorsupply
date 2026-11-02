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

from urllib.parse import quote as url_quote

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
        return self._look_up(production_id, token)[0]

    def _look_up(self, production_id, token):
        """(production, why it was refused).

        FOUR WAYS TO FAIL AND ONE ANSWER was the fault: a sticker that would
        not open said "Not Found" and nothing else, which at a counter is no
        help at all (owner, 2026-10-28: *"when i try scanning the qr code on
        the sticker it leads to a not found page"*). The reason is now
        carried back, and shown to a member of STAFF - never to a stranger,
        who would be reading an answer to a question they should not be
        asking.
        """
        empty = request.env["mrp.production"].sudo().browse()
        production = request.env["mrp.production"].sudo().browse(
            production_id).exists()

        if not production:
            return empty, _("There is no job %s in this database. A sticker"
                            " printed from another database - the test site,"
                            " say - will not open here.", production_id)

        if production.aa_station_kind != "kit":
            return empty, _("Job %s is not a hardware kit (%s), so it has no"
                            " box.", production.display_name,
                            production.aa_station_kind or _("no station"))

        # Compared in constant time, so the route cannot be turned into a way
        # of measuring how close a guess was.
        if not consteq(token or "", production._aa_box_token()):
            return empty, _("That code is not this job's. The link is signed"
                            " with this database's own secret, so a sticker"
                            " printed from the test site will never open on"
                            " the live one, and the other way about.")

        return production, None

    def _refuse(self, why):
        """The reason for somebody who works here; a way IN for everybody else.

        THE REASON IS STILL STAFF-ONLY. What changed on 2026-10-28, after
        *"i still get the not found page when scanning the sticker on my
        phone"*, is what a STRANGER gets - and a phone at the counter is a
        stranger, because nobody is signed into Odoo on their own phone. So
        all four reasons were collapsing back into the bare 404 the reason
        page was written to replace, and the man holding the box learnt
        nothing either time.

        Now it offers a sign-in that comes BACK HERE. That is one tap to the
        reason, instead of a dead end.

        It gives away no more than the bare 404 did: the page is the SAME
        whichever of the four reasons it was, so it still cannot be used to
        find out whether a box id exists or how close a guessed token was.
        All it admits is that `/box/` is a route, which werkzeug's own 207
        bytes already admitted to anybody who looked.
        """
        if why and not request.env.user._is_public():
            return request.render("aa_shop_floor.hardware_box_refused",
                                  {"why": why, "sign_in": None})

        return request.render("aa_shop_floor.hardware_box_refused", {
            "why": None,
            # `request.httprequest.full_path` rather than a rebuilt URL: the
            # point is to come back to the link that was actually scanned,
            # character for character, so that signing in proves something
            # about THAT sticker.
            # `safe=""`, or `quote` leaves the slashes alone and the path
            # rides into the query unescaped - which worked in a browser and
            # is still a redirect parameter that has not been quoted.
            "sign_in": "/web/login?redirect=%s" % url_quote(
                request.httprequest.full_path.rstrip("?"), safe=""),
        })

    @http.route("/box/<int:production_id>/<string:token>", type="http",
                auth="public", methods=["GET"], website=False, sitemap=False)
    def box(self, production_id, token, **kwargs):
        production, why = self._look_up(production_id, token)

        if not production:
            return self._refuse(why)

        card = production._aa_hardware_card()

        if not card:
            return self._refuse(
                _("%s has no hardware card yet - nothing has been worked out"
                  " for the box.", production.display_name))

        return request.render("aa_shop_floor.hardware_box_page",
                              self._values(production, card))

    def _values(self, production, card, notice=None, problem=None):
        """The page, plus the dispatch panel for whoever may see it."""
        values = {
            "card": card,
            "company": production.company_id,
            "dispatch": None,
            "dispatch_none": None,
            "dispatch_sign_in": None,
            "notice": notice,
            "problem": problem,
            "production": production,
            "token": production._aa_box_token(),
        }

        if request.env.user.has_group(DISPATCH_GROUP):
            picking = production._aa_dispatch_picking()

            if picking:
                values["dispatch"] = picking._aa_dispatch_scan_state()
            else:
                # NO TRANSFER TO DISPATCH, AND IT DREW NOTHING AT ALL - which
                # on a two-step warehouse is the likeliest thing to happen at
                # the counter. HIS WAREHOUSE DELIVERS IN TWO STEPS
                # (`pick_ship`): confirming an order makes an INTERNAL pick,
                # and the outgoing delivery does not exist until that pick is
                # validated. So a box can be packed, scanned by the right
                # person, and the whole Dispatch section simply not appear.
                #
                # A man holding a box needs to be told which, out of a
                # missing transfer and a missing permission, he is looking
                # at - and silence says neither.
                values["dispatch_none"] = _(
                    "Nothing to dispatch yet: this order has no outgoing"
                    " delivery. On a two-step warehouse the delivery appears"
                    " once the internal pick is validated.")

        elif request.env.user._is_public():
            # A TEAM MEMBER'S OWN PHONE IS NOT SIGNED IN - owner, 2026-10-28,
            # of the whole point of this: *"At pickup, the team scans the box
            # sticker with a phone or tablet."* A shared tablet signs in once
            # and keeps the panel; a phone somebody pulls out of a pocket
            # never has, so it drew the door's figures and NO SIGN THAT
            # DISPATCH EXISTED. Nobody would guess to sign in for a button
            # they have never seen.
            #
            # The same lesson as the refusal page an hour earlier: a phone at
            # the counter is a stranger. One discreet line, and signing in
            # comes back to this very sticker.
            #
            # PUBLIC ONLY. A dealer or a fitter with a portal login is
            # already signed in and signing in again would not give them the
            # panel, so offering it would be a promise that cannot be kept.
            values["dispatch_sign_in"] = "/web/login?redirect=%s" % url_quote(
                request.httprequest.full_path.rstrip("?"), safe="")

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
