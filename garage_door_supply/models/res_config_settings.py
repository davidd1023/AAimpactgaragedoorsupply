from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ONLY THE FLAG ANGLE FALLBACK IS A SETTING.
    #
    # The jamb brackets were a setting while the rule was thought to be "one
    # size, count by height". It is not - a prepared pair ships a graduated mix
    # of four catalogue sizes, picked by door height, so there is nothing for a
    # person to choose and the setting is gone rather than left to mislead. The
    # brackets are found by their part numbers in models/sale_order.py.
    #
    # The flag angle is found by the track's own finish, so this setting is
    # only the fallback for a finish those products do not cover.
    track_prep_flag_product_id = fields.Many2one(
        "product.product",
        string="Flag angle for prepared tracks",
        config_parameter="garage_door_supply.track_prep_flag_product_id",
        domain="[('sale_ok', '=', True)]",
        help="The flag angle added when a vertical track is ordered prepared."
             " Two per pair, one at each top corner. Found by name from the"
             " track's own finish - Flag Angle Black or Flag Angle White - so"
             " this is only the fallback.",
    )
