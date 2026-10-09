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
    @http.route(
        "/door-work-order/new",
        type="http",
        auth="user",
        methods=["GET"],
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
            parsed = Production._door_wo_parse(spec)
        except UserError as error:
            return self._render("refused", {"message": str(error)})

        items, missing = Production._door_wo_plan(parsed)
        existing = Production._door_wo_existing(parsed)

        return self._render("review", {
            "spec": spec,
            "parsed": parsed,
            "items": items,
            "missing": missing,
            "existing": existing,
            "summary": Production._door_wo_summary_text(parsed),
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

        try:
            production, reused = request.env["mrp.production"]._door_wo_create(spec)
        except UserError as error:
            return self._render("refused", {"message": str(error)})

        action = request.env.ref(PRODUCTION_ACTION, raise_if_not_found=False)
        url = "/odoo/m-%s" % production.id

        if action:
            url = "/odoo/action-%s/%s" % (action.id, production.id)

        return self._render("done", {
            "production": production,
            "reused": reused,
            "url": url,
        })
