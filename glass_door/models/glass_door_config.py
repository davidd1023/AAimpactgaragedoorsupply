from odoo import models, fields


class GlassDoorExtrusionProfile(models.Model):
    _name = 'glass.door.extrusion.profile'
    _description = 'Extrusion Profile'
    _order = 'code'

    code = fields.Integer('Code', required=True)
    name = fields.Char('Name', required=True)
    price_per_inch = fields.Float('Price per Inch', digits=(10, 6))
    weight_per_inch = fields.Float('Weight per Inch (lbs)', digits=(10, 6))

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Extrusion code must be unique.'),
    ]


class GlassDoorGlassType(models.Model):
    _name = 'glass.door.glass.type'
    _description = 'Glass Type'
    _order = 'name'

    name = fields.Char('Name', required=True)
    thickness = fields.Selection([
        ('5/16', '5/16"'),
        ('7/16', '7/16"'),
        ('13/16', '13/16" Insulated Laminated'),
    ], string='Thickness', required=True)
    price_per_sqft = fields.Float('Price per Sq Ft', digits=(10, 4))
    weight_per_sqft = fields.Float('Weight per Sq Ft (lbs)', digits=(10, 4))


class GlassDoorInterlayer(models.Model):
    _name = 'glass.door.interlayer'
    _description = 'Glass Interlayer'
    _order = 'name'

    name = fields.Char('Name', required=True)
    price_per_sqft = fields.Float('Price per Sq Ft', digits=(10, 4))


class GlassDoorFrameFinish(models.Model):
    _name = 'glass.door.frame.finish'
    _description = 'Frame Finish'
    _order = 'name'

    name = fields.Char('Name', required=True)
    code = fields.Char('Code')
