"""The days the shop is shut, which no rule can work out."""

from odoo import fields, models

from .sale_order import CLOSED_SETTING


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_pickup_closed_days = fields.Char(
        string="Days closed for pickup",
        config_parameter=CLOSED_SETTING,
        help="Dates the counter is shut, beyond Saturdays and Sundays, as "
             "2026-12-25, 2026-12-26. They are neither counted as labour "
             "days nor offered to a customer to collect on.")
