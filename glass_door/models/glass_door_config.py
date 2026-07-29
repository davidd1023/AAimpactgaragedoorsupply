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
    requires_paint = fields.Boolean(
        'Requires Local Paint',
        help='Mill finish aluminum sent to local paint shop. Paint cost is charged per sq ft.'
    )
    paint_cost_per_sqft = fields.Float(
        'Paint Cost per Sq Ft', digits=(10, 4),
        help='Cost per square foot of door face area when sent to paint.'
    )


class GlassDoorMotor(models.Model):
    _name = 'glass.door.motor'
    _description = 'Door Motor / Opener'
    _order = 'brand, name'

    brand = fields.Char('Brand', required=True)
    name = fields.Char('Model Name', required=True)
    horsepower = fields.Selection([
        ('1/2', '1/2 HP'),
        ('3/4', '3/4 HP'),
        ('1', '1 HP'),
        ('1_1_4', '1-1/4 HP'),
        ('2', '2 HP'),
    ], string='Horsepower')
    drive_type = fields.Selection([
        ('belt', 'Belt Drive'),
        ('chain', 'Chain Drive'),
        ('direct', 'Direct Drive'),
        ('jackshaft', 'Jackshaft'),
    ], string='Drive Type')
    cost = fields.Float('Our Cost', digits=(10, 2),
                        help='Our cost for this unit. Dealer markup is applied on top.')
    active = fields.Boolean(default=True)
