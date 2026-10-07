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

    # THE LABOUR CHARGE, same arrangement as the markup above and for the same
    # reasons: one source of truth, back office only, and written through
    # set_param so every worker drops its cached copy.
    #
    # The customer is not shown this as a line of its own - the calculator
    # quotes one total and the cart charges the same total - but it is part of a
    # figure they are shown, so it can be worked out by comparing two quotes.
    # Nothing can be both included in a price and hidden from the person paying
    # it; see the note in controllers/main.py.
    spring_labor_flat = fields.Float(
        string="Spring assembly labour",
        config_parameter="spring_engineering.labor_flat",
        help="Flat charge added to every custom spring assembly for the work of "
             "building it, on top of the marked-up materials. Per assembly, not "
             "per spring. Zero charges nothing for labour.",
    )

    def set_values(self):
        """Write the two pricing parameters so that ZERO survives the trip.

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
            "spring_engineering.markup_percent", str(self.spring_markup_percent or 0.0)
        )
        params.set_param(
            "spring_engineering.labor_flat", str(self.spring_labor_flat or 0.0)
        )
