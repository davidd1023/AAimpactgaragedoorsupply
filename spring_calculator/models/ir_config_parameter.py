# GENERATED FROM spring_engineering BY tools/build_spring_calculator.py. DO NOT EDIT BY HAND - change the original and re-run the script.
from odoo import api, models

from ..compat import config_rate, set_config_rate
from ..pricing import STEEL_COST_PER_LB, STEEL_PRICE_PER_LB

# THE KEYS KEEP THE `spring_engineering.` PREFIX ON PURPOSE - see the note in
# tools/build_spring_calculator.py. They are internal identifiers nobody
# reads, and leaving them alone is what lets pricing.py and main.py copy
# across untouched.
#
# `markup_percent` is NOT shipped. _markup_factor() has returned 1 since
# 2026-10-16 ("cones and filler at cost, markup setting removed"), so the row
# would be a default for a figure nothing reads.
DEFAULTS = {
    "spring_engineering.steel_per_lb": STEEL_PRICE_PER_LB,
    "spring_engineering.steel_cost_per_lb": STEEL_COST_PER_LB,
}


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _spring_calculator_ensure_defaults(self):
        """Create the pricing parameters if absent. Never overwrite.

        A FUNCTION RATHER THAN `noupdate` RECORDS, which is the original's
        hard-won shape and is kept: set_param DELETES the row when handed a
        falsy value, taking the xmlid with it, and the next module update then
        tries to INSERT a record whose key already exists - which fails the
        whole registry. Addressing the parameter by key cannot collide.

        A STORED "0" IS A VALUE and is left alone; only a missing or blank
        parameter is filled in.
        """
        for key, default in DEFAULTS.items():
            if config_rate(self.env, key) in (None, False, ""):
                set_config_rate(self.env, key, default)
