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

from odoo import http
from odoo.http import request


class AAPickupSlotController(http.Controller):

    @http.route("/shop/pickup_slot", type="jsonrpc", auth="public",
                website=True)
    def aa_set_pickup_slot(self, date=None, slot=None, **kwargs):
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

        if slot is not None:
            values["aa_pickup_slot"] = slot or False

        if values:
            order.write(values)

        return {
            "label": order.aa_pickup_label or "",
            "problem": order._aa_pickup_problem() or "",
        }
