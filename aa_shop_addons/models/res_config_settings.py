"""WHERE THE FALLBACK LOOKS, WHEN THE NAMES ARE NOT THE OBVIOUS ONES.

Four website categories, one per family. Left alone they are found by name -
"Cones", "Cables", "Tracks", "Trims" - which is what the shop calls them on a
catalogue nobody has renamed. These exist so that a category called
"Lift Cables" or "Torsion Cones" does not mean a deploy to point at.

They only affect the FALLBACK. A product with its own Accessory Products set
ignores them entirely.
"""

from odoo import fields, models

from .product_template import FAMILIES, SETTING


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_addon_categ_cones_id = fields.Many2one(
        "product.public.category", string="Cones category",
        config_parameter=SETTING % "cones")
    aa_addon_categ_cables_id = fields.Many2one(
        "product.public.category", string="Cables category",
        config_parameter=SETTING % "cables")
    aa_addon_categ_tracks_id = fields.Many2one(
        "product.public.category", string="Tracks category",
        config_parameter=SETTING % "tracks")
    aa_addon_categ_trims_id = fields.Many2one(
        "product.public.category", string="Trims category",
        config_parameter=SETTING % "trims")

    def aa_addon_families(self):
        """The four, for anything that wants to loop them."""
        return list(FAMILIES)
