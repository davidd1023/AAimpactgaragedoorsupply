"""The days the shop is shut, which no rule can work out."""

from odoo import fields, models

from .pickup_time import (
    DEFAULT_FROM, DEFAULT_TO, FROM_SETTING, TO_SETTING,
)
from .sale_order import CLOSED_SETTING


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_pickup_closed_days = fields.Char(
        string="Days closed for pickup",
        config_parameter=CLOSED_SETTING,
        help="Dates the counter is shut, beyond Saturdays and Sundays, as "
             "2026-12-25, 2026-12-26. They are neither counted as labour "
             "days nor offered to a customer to collect on.")

    aa_pickup_open_from = fields.Float(
        string="Counter opens", config_parameter=FROM_SETTING,
        default=DEFAULT_FROM,
        help="The first time of day a customer may choose to collect, in "
             "hours - 7.0 is 7:00 AM. The times offered run from here to "
             "the closing time in half hours.")
    aa_pickup_open_to = fields.Float(
        string="Counter closes", config_parameter=TO_SETTING,
        default=DEFAULT_TO,
        help="The last time of day a customer may choose - 16.0 is 4:00 PM.")
