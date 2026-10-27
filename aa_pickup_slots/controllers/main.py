"""SAVING THE SLOT AS THE CUSTOMER CHOOSES IT.

The same shape as Odoo's own delivery-method route next door: a jsonrpc call
from the checkout page, writing on the cart, answering with what the page
should now say.

THE DAY IS CHECKED HERE AS WELL AS AT PAYMENT. A select box is a suggestion,
not a constraint - anybody can post this route a date - and a pickup booked
for a Sunday or for tomorrow is a customer standing at a locked door. The
same `_aa_pickup_problem` the payment gate uses decides, so the two can never
disagree.
"""

from odoo import _, http
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class AAPickupSlotController(http.Controller):

    @http.route("/shop/pickup_slot", type="jsonrpc", auth="public",
                website=True)
    def aa_set_pickup_slot(self, date=None, time=None, **kwargs):
        order = request.website.sale_get_order()

        if not order:
            return {"error": "no-cart"}

        order = order.sudo()
        allowed = {day.isoformat() for day, _label in order._aa_pickup_choices()}
        values = {}

        if date is not None:
            if date and date not in allowed:
                return {"problem": "That day is not available to collect on.",
                        "label": order.aa_pickup_label or ""}

            values["aa_pickup_date"] = date or False

        if time is not None:
            # A time of day, in hours. Anything that is not a number we are
            # open at is refused by _aa_pickup_problem on the way out.
            try:
                values["aa_pickup_time"] = float(time) or False
            except (TypeError, ValueError):
                values["aa_pickup_time"] = False

        if values:
            order.write(values)

        return {
            "label": order.aa_pickup_label or "",
            "problem": order._aa_pickup_problem() or "",
        }


class AAWebsiteSalePickup(WebsiteSale):
    """THE GATE THAT ACTUALLY STOPS THEM.

    `_check_cart_is_ready_to_be_paid` is only reached on the zero-total path
    in Odoo 19, so a pickup order with something to pay sailed past it -
    owner, 2026-10-27: "currently they dont need to do either to proceed".

    `_get_shop_payment_errors` is the one the payment page actually consults,
    and the one `/shop/payment/validate` raises on. Both are overridden now:
    this for the readable message, and the other left in place because it is
    the documented hook and something else may call it.
    """

    def _get_shop_payment_errors(self, order):
        errors = super()._get_shop_payment_errors(order)
        problem = order._aa_pickup_problem()

        if problem:
            errors.append((_("Pickup time needed"), problem))

        return errors
