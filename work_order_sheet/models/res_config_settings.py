"""WHICH OF OUR ADDRESSES TELLS THE CUSTOMER THEIR ORDER IS READY.

The owner, 2026-10-19: "we need to make it so that we can input and edit which
of our emails is sending the alert in the settings". So it is a setting in
Inventory > Settings, beside the delivery confirmation it belongs with, and not
a line of code.

CHECKED WHEN IT IS SAVED, not when the first customer is emailed. A typo in a
from-address does not fail loudly: the mail goes out from somewhere else, or
goes out and bounces into a mailbox nobody reads, and the shop finds out when a
customer who was never told rings up asking where their order is. It is a
minute's work to refuse it here and no work at all to fix it.
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.mail import email_normalize, single_email_re

READY_FROM = "work_order_sheet.ready_email_from"
READY_AUTO = "work_order_sheet.ready_email_auto"
READY_SINCE = "work_order_sheet.ready_auto_since"

# "AA Impact Garage Door <sales@aaigd.com>" -> what is between the angles.
INSIDE_ANGLES = re.compile(r"[^<>]*<([^<>]+)>")


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _work_order_sheet_ready_since(self):
        """Stamp the day automatic alerts started, once and once only.

        Called from the data file on every module update, and does nothing at
        all after the first time: the point of it is that the sweep has a line
        to start from, so switching this feature on does not email every
        customer whose order has been sitting ready since before it existed.
        """
        if not self.sudo().get_param(READY_SINCE):
            self.sudo().set_param(READY_SINCE, fields.Datetime.now())

        return True


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dispatch_ready_email_auto = fields.Boolean(
        string="Tell customers automatically when their order is ready",
        default=True,
        config_parameter=READY_AUTO,
        help="Sends the \"your order is ready\" email by itself, within a few "
             "minutes of the delivery becoming ready - which for a made-to-order "
             "door is when the shop has finished making it. The button on the "
             "delivery stays either way, for sending it again.")
    dispatch_ready_email_from = fields.Char(
        string="Order-ready alerts are sent from",
        config_parameter=READY_FROM,
        help="The address the \"your order is ready\" email comes from, and "
             "the one a customer's reply goes back to. Left empty, the "
             "company's own email address is used.")

    @api.constrains("dispatch_ready_email_from")
    def _check_dispatch_ready_email_from(self):
        for settings in self:
            typed = (settings.dispatch_ready_email_from or "").strip()

            if not typed:
                continue

            # ACCEPTS "AA Impact <sales@aaigd.com>" as well as the bare
            # address, because that is what somebody types when they want the
            # shop's name on the message.
            #
            # CHECKED ON THE RAW TEXT, which is the whole lesson this
            # repository learnt on the signup form and which I had just walked
            # into again: email_normalize REWRITES rather than refuses - it
            # turns "a b@c.com" into "b@c.com" - so validating what it returns
            # is validating something the owner did not type. The strict
            # pattern gets the text as typed; normalize is only used
            # afterwards, to lower-case what was accepted.
            inside = INSIDE_ANGLES.fullmatch(typed)
            address = (inside.group(1) if inside else typed).strip()

            if not single_email_re.fullmatch(address) or not email_normalize(address):
                raise ValidationError(_(
                    "%(typed)s is not an email address we can send from. Use "
                    "something like sales@aaigd.com, or leave it empty to "
                    "send from the company's own address.",
                    typed=typed,
                ))
