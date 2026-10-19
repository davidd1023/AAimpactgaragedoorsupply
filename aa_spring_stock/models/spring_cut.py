from odoo import fields, models


class AaSpringCut(models.Model):
    """One spring cut from one coil piece: the cut history."""

    _name = "aa.spring.cut"
    _description = "Spring Cut"
    _order = "date desc, id desc"

    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    production_id = fields.Many2one("mrp.production", string="Manufacturing Order", index=True,
                                    ondelete="cascade")
    wo_number = fields.Char(string="W/O #", related="production_id.aa_wo_number", store=True)
    origin = fields.Char(string="Sale Order", related="production_id.origin", store=True)
    role = fields.Char(string="Spring")
    hand = fields.Selection([("L", "LH"), ("R", "RH")], string="Hand")
    wire = fields.Char(string="Wire")
    inside_diameter = fields.Char(string="I.D.")
    product_id = fields.Many2one("product.product", string="Coil")
    lot_id = fields.Many2one("stock.lot", string="Piece")
    source = fields.Selection([("Rack", "Rack"), ("Floor", "Floor"), ("Boxes", "Boxes")],
                              string="Cut From")
    length = fields.Float(string="Length (in)", digits=(16, 2))
    remaining = fields.Float(string="Piece Left (in)", digits=(16, 2))
    state = fields.Selection([
        ("planned", "Planned"),
        ("done", "Cut"),
        ("short", "No Coil Available"),
        ("untracked", "Coil Not in Inventory"),
    ], default="planned", required=True, index=True)
    note = fields.Char()
