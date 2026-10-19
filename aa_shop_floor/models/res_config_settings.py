"""WHAT THE STICKER IS PRINTED ON, as a setting rather than as code.

"We don't know what sticker size we are going to use yet" (owner, 2026-10-19).
So the size is a choice in Manufacturing > Settings - the common label stock by
name, or any size at all typed in inches - and the label lays itself out to fit
whatever is chosen. A size nobody has settled on does not belong in a report
template that has to be edited and deployed to change it.

THE SETTING IS THE TRUTH, not the paper format. The format record is written
from the setting (see _aa_sticker_apply_size) and re-written on every module
update, so the owner's choice survives an update instead of being quietly put
back to whatever shipped.
"""

from odoo import fields, models

# THE LABEL STOCK, by the names it is sold under. Inches, because that is how
# it is sold here - 4 x 6 is the shipping label every thermal printer takes,
# 2 1/4 x 1 1/4 is the small roll.
#
# The key holds the size, so there is no second table to keep in step: "4x3"
# is four inches by three.
STICKER_SIZES = [
    ("4x6", "4 x 6 in (shipping label)"),
    ("4x4", "4 x 4 in"),
    ("4x3", "4 x 3 in"),
    ("4x2", "4 x 2 in"),
    ("3x2", "3 x 2 in"),
    ("2.25x1.25", "2 1/4 x 1 1/4 in (small roll)"),
    ("8.5x11", "8 1/2 x 11 in (plain paper)"),
    ("custom", "Custom size"),
]

DEFAULT_STICKER_SIZE = "4x6"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_sticker_size = fields.Selection(
        STICKER_SIZES, string="Hardware sticker size",
        default=DEFAULT_STICKER_SIZE,
        config_parameter="aa_shop_floor.sticker_size",
        help="What the hardware box's sticker is printed on. The label lays "
             "itself out to fit, so a smaller sticker prints smaller type "
             "rather than running onto a second label.")
    aa_sticker_width_in = fields.Float(
        string="Sticker width (in)", default=4.0,
        config_parameter="aa_shop_floor.sticker_width_in")
    aa_sticker_height_in = fields.Float(
        string="Sticker height (in)", default=6.0,
        config_parameter="aa_shop_floor.sticker_height_in")

    def set_values(self):
        super().set_values()
        # The parameters are saved by now, so the format is written from them
        # rather than from these fields - one path, the same one an update
        # takes.
        self.env["mrp.production"]._aa_sticker_apply_size()
