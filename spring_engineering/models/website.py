from odoo import fields, models


class Website(models.Model):
    """The least this shop will take as an order."""

    _inherit = "website"

    # ON THE WEBSITE, NOT IN A SYSTEM PARAMETER.
    #
    # The markup and the labour charge are ir.config_parameter values because
    # they are about pricing one product and there is one of each. A minimum
    # order is a RULE OF THE SHOP: it belongs to the site the customer is
    # buying from, in that site's currency, and a second site would want its
    # own. Keeping it here also means zero is simply zero - a config_parameter
    # set to a falsy value deletes its own row, which is the trap set_values
    # in res_config_settings.py has to work around for the other three.
    aa_minimum_order_amount = fields.Float(
        string="Minimum order",
        digits="Product Price",
        help="The smallest order this website will accept. A cart worth less"
             " than this can be filled and changed, but not checked out, and"
             " the shortfall is shown on the cart. Zero means no minimum.",
    )
