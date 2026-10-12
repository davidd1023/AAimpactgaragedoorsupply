from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Which stock items the cut lengths come from.

    CONFIGURATION RATHER THAN CODE, because the live catalogue cannot be read
    from a development build - this database is created fresh, not copied from
    production, so any part number written into the source here would be a
    guess. The cable reels are guessed at once, by name, and only as a default
    that the setting overrides; a wrong guess shows up as a named missing
    setting on the review page rather than as a silently wrong component.
    """

    _inherit = "res.config.settings"

    door_wo_job_product_id = fields.Many2one(
        "product.product",
        string="Work Order Product",
        config_parameter="door_work_order.job_product_id",
        help="The product each door's manufacturing order is raised against.",
    )
    door_wo_track_2_product_id = fields.Many2one(
        "product.product",
        string='2" Track Stock',
        config_parameter="door_work_order.track_2_product_id",
        help='The stock length that 2" tracks are cut from.',
    )
    door_wo_track_3_product_id = fields.Many2one(
        "product.product",
        string='3" Track Stock',
        config_parameter="door_work_order.track_3_product_id",
        help='The stock length that 3" tracks are cut from.',
    )
    door_wo_cable_18_product_id = fields.Many2one(
        "product.product",
        string='1/8" Cable Reel',
        config_parameter="door_work_order.cable_18_product_id",
    )
    door_wo_cable_532_product_id = fields.Many2one(
        "product.product",
        string='5/32" Cable Reel',
        config_parameter="door_work_order.cable_532_product_id",
    )
    door_wo_cable_316_product_id = fields.Many2one(
        "product.product",
        string='3/16" Cable Reel',
        config_parameter="door_work_order.cable_316_product_id",
    )
    # OFF BY DEFAULT, and that is a decision rather than an oversight. A work
    # instruction is right the moment it carries the cut list; booking material
    # out of stock is a separate claim about how the shop counts a 500 ft reel
    # against 20 ft taken off it, and nobody has said how they want that
    # counted. A wrong component line is worse than an absent one, because it
    # looks like an answer.
    door_wo_consume_components = fields.Boolean(
        string="Book Material On The Order",
        config_parameter="door_work_order.consume_components",
        help="Add the stock items as components of the manufacturing order."
             " Leave this off to raise the order as a cut instruction only.",
    )
