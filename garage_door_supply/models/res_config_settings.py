from odoo import fields, models


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
             " The quantity comes from the door height: 3 per track for a 6-7 ft"
             " door, 4 for 8-9 ft, 5 for 10-12 ft.",
    )
    track_prep_flag_product_id = fields.Many2one(
        "product.product",
        string="Flag angle for prepared tracks",
        config_parameter="garage_door_supply.track_prep_flag_product_id",
        domain="[('sale_ok', '=', True)]",
        help="The flag angle added when a vertical track is ordered prepared."
             " One per track.",
    )
