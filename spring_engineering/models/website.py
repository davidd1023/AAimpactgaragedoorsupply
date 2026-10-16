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
    # WHETHER A NEW ACCOUNT HAS TO PROVE ITS ADDRESS.
    #
    # A switch rather than a certainty, because this is the one rule here
    # that can keep a real customer out: if the shop's mail ever stops going
    # out, every new signup is stranded, and the owner needs a way to open
    # the door again without a deploy. Turning it off stops NEW accounts
    # being held; it does not confirm the ones already waiting, which is on
    # purpose - those are set from the user form or by following the link.
    aa_require_email_confirmation = fields.Boolean(
        string="Confirm email addresses",
        default=True,
        help="A customer who signs up on the website is sent a link and"
             " cannot sign in until they follow it. Invited customers are"
             " unaffected: their address is proven by the invitation.",
    )

    # THE MOST ONE LINE OF A CART MAY HOLD.
    #
    # The quantity box on a product page is a TEXT field with a data-min the
    # browser does not enforce, so what arrives at the server is whatever the
    # customer typed - including a thousand thousand, or minus one. Per LINE
    # rather than per order, on the owner's instruction: a cart may hold a
    # thousand brackets and a thousand rollers, and adding one of something
    # new is never refused because of what else is in the basket. It also
    # cannot fight the parts this module adds by itself - a prepared track
    # brings brackets, and every bracket brings a stud and a nut.
    aa_maximum_line_quantity = fields.Integer(
        string="Maximum per item",
        default=1000,
        help="The most of any one product a customer may put in an order."
             " What they ask for beyond it is not added, and they are told"
             " why. Zero means no limit.",
    )

    aa_minimum_order_amount = fields.Float(
        string="Minimum order",
        digits="Product Price",
        help="The smallest order this website will accept. A cart worth less"
             " than this can be filled and changed, but not checked out, and"
             " the shortfall is shown on the cart. Zero means no minimum.",
    )
