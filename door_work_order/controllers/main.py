import json
import logging

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

# The action the finished order is shown in. Named rather than guessed at a URL
# because /odoo/<path> formats have changed between versions and an action id
# has not.
PRODUCTION_ACTION = "mrp.mrp_production_action"


class DoorWorkOrder(http.Controller):
    """Takes a door from the shop's calculator and raises its work order.

    AUTH="USER", WHICH IS THE WHOLE SECURITY MODEL. The calculator is a public
    page on github.io and cannot be trusted with a secret - anything embedded
    in it can be read by viewing source - so this does not accept a token. It
    accepts a logged-in Odoo session instead: a visitor who is not signed in
    gets the login page, and the order records who raised it. The spec in the
    URL is therefore a request from a known employee, not an anonymous one.
    """

    def _check_access(self):
        if not request.env.user.has_group("mrp.group_mrp_user"):
            raise AccessError(
                _("You need Manufacturing access to raise a door work order.")
            )

    def _render(self, template, values):
        return request.render("door_work_order.%s" % template, values)

    # --- step one: show what would be made -----------------------------------
    #
    # A GET THAT CHANGES NOTHING. This could create the order outright and
    # redirect to it, which would be one click instead of two - and would also
    # mean any page, anywhere, could make a logged-in employee's browser raise
    # manufacturing orders by loading an image. It would equally mean a
    # mistyped door becomes a record before anyone reads it. So the link shows
    # the cut list and asks; the creating is a POST with the session's token.
    # POST IS ACCEPTED BECAUSE A LONG ORDER DOES NOT FIT IN A URL. A mark is
    # about 500 bytes once encoded, so fifteen of them pass the 8 kB request
    # line most proxies allow and the person gets a bare 414 from something in
    # front of Odoo rather than this module's own refusal page. The body has no
    # such limit.
    #
    # csrf=False is safe HERE and only here: this route reads and renders, it
    # creates nothing. The route that creates keeps its token. A cross-site
    # POST to this one can at worst show a signed-in employee a page.
    @http.route(
        "/door-work-order/new",
        type="http",
        auth="user",
        methods=["GET", "POST"],
        csrf=False,
        website=False,
        sitemap=False,
    )
    def door_work_order_new(self, spec=None, **kwargs):
        try:
            self._check_access()
        except AccessError as error:
            return self._render("refused", {"message": str(error)})

        Production = request.env["mrp.production"]

        try:
            # THE WHOLE ORDER, not one door. This read _door_wo_parse while the
            # creating path had already moved to _door_wo_parse_order, so an
            # order carrying marks was refused here - on the top-level "track"
            # that a multi-mark payload does not have - and never reached the
            # button at all. The two must read the same shape, which is why
            # there is now an HTTP test on the multi-mark payload.
            order = Production._door_wo_parse_order(spec)
        except UserError as error:
            return self._render("refused", {"message": str(error)})

        doors = []
        missing = []

        for parsed in order["doors"]:
            items, gaps = Production._door_wo_plan(parsed)
            doors.append({
                "parsed": parsed,
                "items": items,
                "summary": Production._door_wo_summary_text(parsed),
            })

            for gap in gaps:
                if gap not in missing:
                    missing.append(gap)

        existing = Production._door_wo_existing(order)
        on_order = set(existing.door_wo_mark_ids.mapped("label")) if existing else set()

        return self._render("review", {
            "spec": spec,
            "order": order,
            "doors": doors,
            "total_doors": sum(d["parsed"]["door_qty"] for d in doors),
            "missing": missing,
            "existing": existing,
            # WHAT SENDING AGAIN WILL ACTUALLY DO, named rather than implied.
            "new_marks": [d["parsed"]["mark"] for d in doors
                          if d["parsed"]["mark"] not in on_order],
            "kept_marks": sorted(on_order),
        })

    # --- step two: raise it ---------------------------------------------------
    @http.route(
        "/door-work-order/create",
        type="http",
        auth="user",
        methods=["POST"],
        website=False,
        sitemap=False,
    )
    def door_work_order_create(self, spec=None, **kwargs):
        try:
            self._check_access()
        except AccessError as error:
            return self._render("refused", {"message": str(error)})

        Production = request.env["mrp.production"]

        # WHAT WAS ON THE ORDER BEFORE, so the page afterwards can say what
        # actually happened. "reused" alone cannot tell "this order already
        # existed and nothing changed" from "this order already existed and
        # mark B was just added to it" - and the whole point of the second case
        # is that the mark reaches the floor, which the page was not confirming.
        try:
            order = Production._door_wo_parse_order(spec)
            existing = Production._door_wo_existing(order)
            before = set(existing.door_wo_mark_ids.mapped("label")) if existing else set()
            production, reused = Production._door_wo_create(spec)
        except UserError as error:
            return self._render("refused", {"message": str(error)})

        added = [label for label in production.door_wo_mark_ids.mapped("label")
                 if label and label not in before]

        action = request.env.ref(PRODUCTION_ACTION, raise_if_not_found=False)
        url = "/odoo/m-%s" % production.id

        if action:
            url = "/odoo/action-%s/%s" % (action.id, production.id)

        return self._render("done", {
            "production": production,
            "reused": reused,
            "added": added if reused else [],
            "url": url,
        })
