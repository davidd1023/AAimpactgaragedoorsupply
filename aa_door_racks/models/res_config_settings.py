from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_rack_panel_thickness = fields.Float(
        string="Panel thickness (in)", config_parameter="aa_door_racks.panel_thickness", default=3.0)
    aa_rack_spacer = fields.Float(
        string="Board between doors (in)", config_parameter="aa_door_racks.spacer", default=1.5)
    aa_rack_two_arm_max = fields.Float(
        string="Longest door on two arms (in)", config_parameter="aa_door_racks.two_arm_max", default=120.0)
    aa_rack_fallback_max = fields.Float(
        string="Longest door on one unit when 3 arms are out of reach (in)",
        config_parameter="aa_door_racks.fallback_max", default=132.0)
