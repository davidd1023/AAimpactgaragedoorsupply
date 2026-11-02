# GENERATED FROM spring_engineering BY tools/build_spring_calculator.py. DO NOT EDIT BY HAND - change the original and re-run the script.
from odoo import fields, models

from ..compat import set_config_rate


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def set_values(self):
        """Write the rates so that ZERO survives the trip.

        Odoo stores a `config_parameter` field by handing its value to
        set_param, and a falsy value there does not store a zero - it DELETES
        the row. The reader in controllers/main.py refuses to quote when a
        parameter is missing, on purpose, so a deliberate 0 typed into this
        form would otherwise turn every quote into "call us". Writing the
        figures explicitly as strings keeps both halves.
        """
        super().set_values()

        set_config_rate(self.env, "spring_engineering.steel_per_lb",
                        self.spring_steel_per_lb or 0.0)
        set_config_rate(self.env, "spring_engineering.steel_cost_per_lb",
                        self.spring_steel_cost_per_lb or 0.0)

    # THE SELL RATE: cost + winding labour + margin, per pound. It is NOT
    # marked up again - see pricing.py.
    spring_steel_per_lb = fields.Float(
        string="Spring sell price per pound",
        config_parameter="spring_engineering.steel_per_lb",
    )
    # A SECOND FIGURE, not a division of the first: no arithmetic on a sell
    # rate with labour inside it can recover a cost. Nothing a customer sees
    # is priced from this.
    spring_steel_cost_per_lb = fields.Float(
        string="Spring steel cost per pound",
        config_parameter="spring_engineering.steel_cost_per_lb",
    )
