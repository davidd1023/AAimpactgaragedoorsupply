"""WHERE THE FALLBACK LOOKS, WHEN THE NAMES ARE NOT THE OBVIOUS ONES.

Four website categories, one per family. Left alone they are found by name -
"Cones", "Cables", "Tracks", "Trims" - which is what the shop calls them on a
catalogue nobody has renamed. These exist so that a category called
"Lift Cables" or "Torsion Cones" does not mean a deploy to point at.

They only affect the FALLBACK. A product with its own Alternative Products set
ignores them entirely.

Beside them is the one number the automatic recommendations need: HOW MANY
ORDERS make a habit. It is a setting rather than a constant because the answer
depends on how much history there is, and that is not something to need a
deploy for - set it to 1 on a young catalogue and watch what comes out, raise
it when there is enough to be choosy.
"""

from odoo import fields, models

from .addon_suggestion import MIN_ORDERS, MIN_ORDERS_SETTING
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

    aa_addon_min_orders = fields.Integer(
        string="Orders before recommending", default=MIN_ORDERS,
        config_parameter=MIN_ORDERS_SETTING,
        help="How many of your own orders have to carry two products together"
             " before one is recommended under the other. Two, because one is"
             " an anecdote.")

    def aa_addon_families(self):
        """The four, for anything that wants to loop them."""
        return list(FAMILIES)

    def action_aa_addon_rebuild(self):
        """Count the orders again now, rather than waiting for tonight.

        The number above is the thing somebody will want to try two values of,
        and a setting that cannot be tried is a setting nobody touches.
        """
        self.ensure_one()
        self.env["aa.addon.suggestion"]._aa_rebuild()

        return self.env["ir.actions.actions"]._for_xml_id(
            "aa_shop_addons.action_aa_addon_suggestion")
