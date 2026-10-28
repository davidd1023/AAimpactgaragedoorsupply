from odoo import api, models

from ..pricing import STEEL_COST_PER_LB, STEEL_PRICE_PER_LB

# The figures the module ships with. The markup is a percentage; the labour
# charge is currency, flat per assembly. Both are read by controllers/main.py,
# which refuses to quote a price if either is missing - so these exist to make
# sure a fresh database can quote at all, and not to hold the live values.
DEFAULTS = {
    "spring_engineering.markup_percent": "80",
    # The steel rate's default comes from pricing.py so there is one place it is
    # written down, rather than a second copy here that could drift from it.
    "spring_engineering.steel_per_lb": str(STEEL_PRICE_PER_LB),
    # WHAT THE STEEL COSTS, as against what it sells for. Nothing a customer
    # sees is priced from it - it is what the staff-only cost line on the cart
    # works a spring out from - so a missing row costs a figure on a staff
    # page rather than quoting wrongly, and pricing.py holds its default for
    # the same reason it holds the sell rate's.
    "spring_engineering.steel_cost_per_lb": str(STEEL_COST_PER_LB),
}


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _spring_engineering_ensure_defaults(self):
        """Create the pricing parameters if they are absent. Never overwrite.

        Called from views/spring_engineering_settings.xml on install and on
        every module update, which is the behaviour the old `noupdate` records
        were reaching for - and unlike those records this cannot collide with a
        row that lost its xmlid, because it addresses the parameter by key.

        A STORED "0" IS A VALUE AND IS LEFT ALONE. get_param returns the string,
        and "0"  and "0.0" are both non-empty, so a deliberate zero markup or
        zero labour charge survives an upgrade. Only a genuinely missing or
        blank parameter is filled in.
        """
        for key, default in DEFAULTS.items():
            if not self.sudo().get_param(key):
                self.sudo().set_param(key, default)
