import base64
import binascii
import re

from odoo import fields, http
from odoo.http import request
from odoo.tools import consteq

# A drawn signature arrives as a data URL. Only PNG, because that is what the
# pad produces, and bounded because a public route must not be a way to post
# anything of any size into the database.
SIGNATURE = re.compile(r"^data:image/png;base64,([A-Za-z0-9+/=\s]+)$")
MAX_SIGNATURE = 2 * 1024 * 1024


class DeliveryConfirmation(http.Controller):
    """The customer's own page: what they were handed, and their name on it.

    PUBLIC, AND THE LINK IS THE KEY, exactly as the bench screens are. The page
    shows one delivery and nothing else - no catalogue, no other orders, no way
    to reach the back office - so the worst a leaked link can do is show
    somebody what was on one order and let them sign for it, which is also the
    worst a leaked paper delivery note can do.
    """

    def _picking(self, token):
        token = (token or "").strip()

        if len(token) < 32:
            return request.env["stock.picking"].sudo().browse()

        picking = request.env["stock.picking"].sudo().search(
            [("dispatch_access_token", "!=", False),
             ("dispatch_access_token", "=", token)], limit=1)

        # Compared in constant time as well as matched, so the search cannot be
        # turned into a way of measuring how close a guess was.
        if picking and consteq(picking.dispatch_access_token, token):
            return picking

        return request.env["stock.picking"].sudo().browse()

    def _render(self, picking, message=""):
        return request.render("work_order_sheet.delivery_confirmation", {
            "picking": picking,
            "lines": picking._dispatch_lines(),
            "company": picking.company_id,
            "message": message,
            "token": picking.dispatch_access_token,
        })

    @http.route("/delivery/<string:token>", type="http", auth="public",
                methods=["GET"], website=False, sitemap=False)
    def form(self, token, **kwargs):
        picking = self._picking(token)

        if not picking:
            return request.not_found()

        return self._render(picking)

    @http.route("/delivery/<string:token>/signature.png", type="http",
                auth="public", methods=["GET"], website=False, sitemap=False)
    def signature_image(self, token, **kwargs):
        """The signature itself, behind the same link as the form.

        Served here rather than through /web/image so that reading it needs the
        link and not an Odoo login - the customer has to be able to see what
        they signed.
        """
        picking = self._picking(token)

        if not picking or not picking.dispatch_signature:
            return request.not_found()

        return request.make_response(
            base64.b64decode(picking.dispatch_signature),
            headers=[("Content-Type", "image/png"),
                     ("Cache-Control", "no-store")])

    @http.route("/delivery/<string:token>/sign", type="http", auth="public",
                methods=["POST"], website=False, sitemap=False, csrf=False)
    def sign(self, token, **post):
        """Record what the customer confirmed, and their signature.

        ONCE. A signed form cannot be signed again - the second signature
        would overwrite the first, and a receipt that can be rewritten is not
        a receipt. Re-opening the link shows what was signed and when.
        """
        picking = self._picking(token)

        if not picking:
            return request.not_found()

        if picking.dispatch_signed_on:
            return request.redirect("/delivery/%s" % token)

        name = (post.get("signed_by") or "").strip()[:120]
        signature = (post.get("signature") or "").strip()
        ticked = [
            int(key[5:]) for key in post
            if key.startswith("item_") and key[5:].isdigit()
        ]

        if not name:
            return self._render(picking, request.env._(
                "Please type your name before signing."))

        if len(signature) > MAX_SIGNATURE:
            return self._render(picking, request.env._(
                "That signature is too large to save. Please try again."))

        drawn = SIGNATURE.match(signature)

        if not drawn:
            return self._render(picking, request.env._(
                "Please sign in the box before confirming."))

        try:
            image = base64.b64encode(
                base64.b64decode(drawn.group(1), validate=False))
        except (binascii.Error, ValueError):
            return self._render(picking, request.env._(
                "That signature could not be saved. Please try again."))

        if not ticked:
            return self._render(picking, request.env._(
                "Please tick the items you received."))

        lines = picking._dispatch_lines()
        confirmed = lines.filtered(lambda move: move.id in ticked)
        confirmed.sudo().write({"dispatch_received": True})
        (lines - confirmed).sudo().write({"dispatch_received": False})

        picking.sudo().write({
            "dispatch_signed_by": name,
            "dispatch_signature": image,
            "dispatch_signed_on": fields.Datetime.now(),
        })
        picking.sudo()._dispatch_log_signature(confirmed, lines - confirmed)

        return request.redirect("/delivery/%s" % token)
