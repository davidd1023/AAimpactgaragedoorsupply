"""WHICH DELIVERY METHODS MEAN "THEY ARE COMING TO GET IT".

A flag rather than a name match. Odoo has an in-store pickup type of its own
in `website_sale_collect`, but that module is not installed and installing it
would reshape his checkout - store selection, per-store stock - for a
question this answers in one checkbox.

The flag is TICKED ONCE AT INSTALL for anything that looks like a pickup
method (see hooks.py) and is his to change after that. No name matching at
runtime: a rule that cannot be turned off is worse than a box somebody ticks,
because the day he adds "Pickup rate for freight" it would start demanding
slots and there would be no way to say no.
"""

from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    aa_is_pickup = fields.Boolean(
        string="Collected in person",
        help="The customer comes to the counter for this one. Ticking it "
             "makes the checkout ask them for a pickup day and time window, "
             "and refuses payment until they choose.")
