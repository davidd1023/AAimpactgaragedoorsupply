from odoo import api, models

# The figures the module ships with. The markup is a percentage; the labour
# charge is currency, flat per assembly. Both are read by controllers/main.py,
# which refuses to quote a price if either is missing - so these exist to make
# sure a fresh database can quote at all, and not to hold the live values.
DEFAULTS = {
    "spring_engineering.markup_percent": "80",
    "spring_engineering.labor_flat": "100",
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
