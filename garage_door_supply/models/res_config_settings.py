from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # WHICH PARTS A PREPARED TRACK SHIPS WITH, as settings rather than as code.
    #
    # There are four jamb brackets in the catalogue at four prices (J-10 to
    # J-16) and the right one is a trade judgement, not something a program can
    # infer. The flag angle already exists as a product. So both are pointed at
    # from Website > Configuration > Settings, and changing supplier or size is
    # a dropdown rather than a release.
    track_prep_jamb_product_id = fields.Many2one(
        "product.product",
        string="Jamb bracket for prepared tracks",
        config_parameter="garage_door_supply.track_prep_jamb_product_id",
        domain="[('sale_ok', '=', True)]",
        help="The jamb bracket added when a vertical track is ordered prepared."
             " The quantity is one per the inches of door height set below,"
             " rounded up.",
    )
    track_prep_flag_product_id = fields.Many2one(
        "product.product",
        string="Flag angle for prepared tracks",
        config_parameter="garage_door_supply.track_prep_flag_product_id",
        domain="[('sale_ok', '=', True)]",
        help="The flag angle added when a vertical track is ordered prepared."
             " One per track.",
    )
    track_prep_inches_per_bracket = fields.Float(
        string="Inches of door height per jamb bracket",
        config_parameter="garage_door_supply.track_prep_inches_per_bracket",
        default=24.0,
        help="A 7 ft door at 24 inches per bracket takes 4 brackets"
             " (84 / 24 = 3.5, rounded up).",
    )

    @api.onchange("track_prep_inches_per_bracket")
    def _onchange_track_prep_inches_per_bracket(self):
        # A zero or negative spacing would ask for an infinite number of
        # brackets, so it is refused here rather than guarded in six places.
        for record in self:
            if record.track_prep_inches_per_bracket is not None \
                    and record.track_prep_inches_per_bracket <= 0:
                record.track_prep_inches_per_bracket = 24.0
