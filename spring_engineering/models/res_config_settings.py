from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # THE MARGIN, AS A SETTING RATHER THAN A SYSTEM PARAMETER.
    #
    # It is stored as the ir.config_parameter the pricing code reads, so this
    # adds a place to change it and no second source of truth. Settings is a
    # back-office page: the website visitor never sees this field, and never
    # sees the number either - the calculator is sent prices with the markup
    # already in them, not the markup. See controllers/main.py.
    #
    # `config_parameter` also means a write here goes through set_param, which
    # clears the cached value across every worker. Writing the parameter row
    # directly in SQL does not, and the old margin keeps being charged.
    spring_markup_percent = fields.Float(
        string="Spring assembly markup",
        config_parameter="spring_engineering.markup_percent",
        help="Percentage added to the supplier cost of a custom spring "
             "assembly to reach the price quoted and charged. 80 means a "
             "$100 assembly is sold for $180. Zero sells at cost.",
    )
