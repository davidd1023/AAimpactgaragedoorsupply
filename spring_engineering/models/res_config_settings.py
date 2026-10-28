from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def set_values(self):
        """Write the pricing parameter so that ZERO survives the trip.

        Odoo stores a `config_parameter` field by handing its value to
        set_param, and a falsy value there does not store a zero - it DELETES
        the row. So a markup of 0 and a labour charge of 0, both perfectly
        reasonable settings, came back from this page as a missing parameter.

        The reader in controllers/main.py refuses to price when a parameter is
        missing, on purpose: a markup that silently defaults to nothing sells
        every assembly at cost, and nothing on the page or in the cart would
        look wrong while it happened. That guard is worth keeping, which means
        it must not be possible to produce a missing parameter by typing 0 into
        a form - otherwise a deliberate zero reads as a configuration error and
        every quote turns into "call us".

        Writing the figures explicitly as strings keeps both halves: "0.0" is a
        value, so the row stays and zero means zero, while a row that is
        genuinely gone still means somebody deleted it.
        """
        super().set_values()

        params = self.env["ir.config_parameter"].sudo()

        params.set_param(
            "spring_engineering.steel_per_lb", str(self.spring_steel_per_lb or 0.0)
        )
        params.set_param(
            "spring_engineering.steel_cost_per_lb",
            str(self.spring_steel_cost_per_lb or 0.0),
        )

    # THE STEEL RATE, which unlike the markup and the labour charge is not a
    # secret - it is a published commodity price, and the owner asked for it to
    # be an ordinary setting. It is still a COST: the browser receives it with
    # the markup already applied, as it does the cone prices.
    spring_steel_per_lb = fields.Float(
        string="Spring sell price per pound",
        config_parameter="spring_engineering.steel_per_lb",
        help="What a pound of finished spring is SOLD for, labour included. "
             "Not marked up. Charged on every spring, using the weights the "
             "calculator shows. Cones and filler are charged on top, at cost "
             "plus the markup.",
    )

    # WHAT THE STEEL COSTS, which is a second figure and not a division of the
    # first. The rate above is a SELL price with the winding labour and the
    # margin already in it, so no arithmetic on it can produce a cost.
    #
    # NOTHING A CUSTOMER SEES IS PRICED FROM THIS. It is used by the staff-only
    # cost line on the cart, to work a custom spring out the same way the quote
    # works its price out - the same weights, the same cone prices, this rate in
    # place of the sell rate.
    spring_steel_cost_per_lb = fields.Float(
        string="Spring steel cost per pound",
        config_parameter="spring_engineering.steel_cost_per_lb",
        help="What a pound of spring steel COSTS us, before winding and "
             "margin. Used only for the cost figure staff see on the cart - "
             "never for a price a customer is quoted. Left at nothing, a "
             "custom spring is reported as having no cost set rather than "
             "being counted at the price of its cones alone.",
    )

    # THE MINIMUM ORDER, which is a rule of the SITE rather than a number used
    # in a calculation - so it is stored on the website record and only
    # surfaced here. That also keeps a deliberate zero safe: see the note on
    # the field itself and the set_values docstring below.
    aa_require_email_confirmation = fields.Boolean(
        related="website_id.aa_require_email_confirmation",
        readonly=False,
    )

    aa_maximum_line_quantity = fields.Integer(
        related="website_id.aa_maximum_line_quantity",
        readonly=False,
    )

    aa_minimum_order_amount = fields.Float(
        related="website_id.aa_minimum_order_amount",
        readonly=False,
    )

    # ONLY THE FLAG ANGLE FALLBACK IS A SETTING.
    #
    # The jamb brackets were a setting while the rule was thought to be "one
    # size, count by height". It is not - a prepared pair ships a graduated mix
    # of four catalogue sizes, picked by door height, so there is nothing for a
    # person to choose and the setting is gone rather than left to mislead. The
    # brackets are found by their part numbers in spring_engineering/models/sale_order.py.
    #
    # The flag angle is found by the track's own finish, so this setting is
    # only the fallback for a finish those products do not cover.
    track_prep_flag_product_id = fields.Many2one(
        "product.product",
        string="Flag angle for prepared tracks",
        config_parameter="spring_engineering.track_prep_flag_product_id",
        domain="[('sale_ok', '=', True)]",
        help="The flag angle added when a vertical track is ordered prepared."
             " Two per pair, one at each top corner. Found by name from the"
             " track's own finish - Flag Angle Black or Flag Angle White - so"
             " this is only the fallback.",
    )
