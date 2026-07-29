import math
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# Panel thresholds: max door height (inches) per panel count
# 3.375 × (panels + 1) subtracted before dividing by panels
# Pattern: base 4'3-5/8" = 51.625", then +24" per panel
PANEL_THRESHOLDS = [
    (2, 51.625),    # 4'3-5/8"
    (3, 75.625),    # 6'3-5/8"
    (4, 99.625),    # 8'3-5/8"
    (5, 123.625),   # 10'3-5/8"
    (6, 147.625),   # 12'3-5/8"
    (7, 171.625),   # 14'3-5/8"
    (8, 195.625),   # 16'3-5/8"
]

MAX_WIDTH_1_LITE = 144.0    # 12'0" — wider doors require minimum 2 lites
WIDTH_104_REQUIRED = 194.0  # 16'2" — internal reinforcement mandatory above this width


def _round_even_inch(value):
    """Round up to the nearest even inch."""
    inches = math.ceil(value)
    if inches % 2 != 0:
        inches += 1
    return float(inches)


def _compute_panel_height(door_height, num_panels):
    """Panel height formula: (door_height - 3.375 × (panels + 1)) / panels"""
    subtract = 3.375 * (num_panels + 1)
    return (door_height - subtract) / num_panels


def _get_num_panels(door_height):
    for panels, max_h in PANEL_THRESHOLDS:
        if door_height <= max_h:
            return panels
    return 8  # maximum


class GlassDoorOrder(models.Model):
    _name = 'glass.door.order'
    _description = 'Glass Door Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # ── Identification ──────────────────────────────────────────────────────────
    name = fields.Char('Work Order #', readonly=True, copy=False, default='New', tracking=True)
    quote_number = fields.Char('Quote #', readonly=True, copy=False, default='New', tracking=True)

    # ── Parties ─────────────────────────────────────────────────────────────────
    dealer_id = fields.Many2one('res.partner', 'Dealer', required=True,
                                 domain=[('is_dealer', '=', True)], tracking=True)
    dealer_client_id = fields.Many2one('glass.door.dealer.client', 'Client',
                                        tracking=True,
                                        help="The dealer's end customer for this job.")
    job_name = fields.Char('Job Name', required=True, tracking=True)
    po_number = fields.Char('PO #', tracking=True,
                             help="Dealer's purchase order or reference number.")

    # ── Door Specifications ──────────────────────────────────────────────────────
    series = fields.Selection([
        ('1200', 'Series 1200'),
        ('1600', 'Series 1600'),
        ('1800', 'Series 1800'),
    ], string='Series', required=True, tracking=True)

    design_pressure = fields.Selection([
        ('dp15', 'DP 15'),
        ('dp20', 'DP 20'),
        ('dp25', 'DP 25'),
        ('dp30', 'DP 30'),
        ('dp35', 'DP 35'),
        ('dp40', 'DP 40'),
        ('dp50', 'DP 50'),
    ], string='Design Pressure', required=True, tracking=True)

    lites = fields.Integer('Lites', default=1, required=True, tracking=True,
                            help='Number of vertical glass sections per panel (1–5).')
    frame_finish_id = fields.Many2one('glass.door.frame.finish', 'Frame Finish', required=True)
    frame_width = fields.Float('Width (inches)', required=True, digits=(10, 3), tracking=True)
    frame_height = fields.Float('Height (inches)', required=True, digits=(10, 3), tracking=True)
    glass_type_id = fields.Many2one('glass.door.glass.type', 'Glass Type', required=True)
    interlayer_id = fields.Many2one('glass.door.interlayer', 'Interlayer', required=True)
    quantity = fields.Integer('Quantity', default=1, required=True)
    door_image = fields.Image('Door Image', max_width=1024, max_height=1024)

    trim_type = fields.Selection([
        ('pvc', 'PVC (Standard)'),
        ('aluminum', 'Aluminum'),
    ], string='Trim Type', default='pvc', required=True)

    hardware_color = fields.Selection([
        ('mill', 'Mill Finish'),
        ('white', 'White'),
        ('black', 'Black'),
    ], string='Hardware Color', default='mill', required=True,
       help='Color of hinges, handles, springs, and other hardware.')

    track_type = fields.Selection([
        ('standard', 'Standard Lift'),
        ('high_lift', 'High Lift'),
        ('vertical', 'Full Vertical Lift'),
        ('low_headroom', 'Low Headroom'),
    ], string='Track Type', default='standard', required=True,
       help='Standard: door follows a standard arc. High Lift/Vertical: clears more headroom. '
            'Low Headroom: limited space above opening.')

    motor_id = fields.Many2one(
        'glass.door.motor', 'Motor / Opener',
        help='Leave blank for door-only orders. Motor cost is subject to dealer markup.'
    )

    job_markup = fields.Float(
        'Job Markup (%)', digits=(5, 2), default=0.0,
        help='Extra markup for this specific job, added on top of the client\'s standard markup.'
    )

    include_reinforcement = fields.Boolean(
        'Add Internal Reinforcement (104)',
        help='Automatically enabled for doors wider than 16\'2". Can also be manually requested '
             'to increase design pressure.',
    )

    # ── Misc Add-on Items ────────────────────────────────────────────────────────
    misc_line_ids = fields.One2many(
        'glass.door.order.misc.line', 'order_id', 'Miscellaneous Items',
        help='Extra items quoted on this order (handles, remotes, installation hardware, etc.). '
             'Dealer enters sell price — not subject to the markup calculation.'
    )

    # ── Computed Door Properties ─────────────────────────────────────────────────
    num_panels = fields.Integer('Panels', compute='_compute_door_properties', store=True)
    panel_height = fields.Float('Panel Height (in)', compute='_compute_door_properties',
                                 store=True, digits=(10, 4))
    glass_width = fields.Float('Glass Width (in)', compute='_compute_door_properties',
                                store=True, digits=(10, 3))
    glass_height = fields.Float('Glass Height (in)', compute='_compute_door_properties',
                                 store=True, digits=(10, 3))
    door_weight = fields.Float('Door Weight (lbs)', compute='_compute_weight',
                                store=True, digits=(10, 2))

    # ── Pricing ──────────────────────────────────────────────────────────────────
    unit_price = fields.Float('Unit Price', compute='_compute_price', store=True, digits=(10, 2))
    total_price = fields.Float('Total Price', compute='_compute_price', store=True, digits=(10, 2))

    # ── Status ───────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('cutting', 'Cutting'),
        ('punching', 'Punching'),
        ('prepping', 'Prepping'),
        ('assembly', 'Assembly'),
        ('glazing', 'Glazing'),
        ('packing', 'Packing'),
        ('ready_pickup', 'Ready for Pickup'),
        ('ready_ship', 'Ready to Ship'),
    ], default='draft', tracking=True, required=True, string='Status')

    # ── Cutting List ─────────────────────────────────────────────────────────────
    extrusion_line_ids = fields.One2many(
        'glass.door.extrusion.line', 'order_id', 'Cutting List'
    )

    # ── Helpers ──────────────────────────────────────────────────────────────────
    reinforcement_required = fields.Boolean(
        compute='_compute_door_properties', store=True,
        string='Reinforcement Required (auto)',
    )

    # ─────────────────────────────────────────────────────────────────────────────
    # Computed methods
    # ─────────────────────────────────────────────────────────────────────────────

    @api.depends('frame_width', 'frame_height', 'lites', 'glass_type_id')
    def _compute_door_properties(self):
        for order in self:
            h = order.frame_height or 0.0
            w = order.frame_width or 0.0
            l = max(order.lites or 1, 1)

            # Panel count
            n = _get_num_panels(h) if h > 0 else 0
            order.num_panels = n

            # Panel height
            ph = _compute_panel_height(h, n) if n > 0 else 0.0
            order.panel_height = ph

            # Glass dimensions (rounded to nearest even inch)
            # Width: same denominator as horizontal glass stop
            raw_gw = (w - 6.5 - 2.0 * (l - 1)) / l if w > 0 and l > 0 else 0.0
            order.glass_width = _round_even_inch(raw_gw) if raw_gw > 0 else 0.0

            # Height: panel height minus glass stop offset
            raw_gh = ph - 1.374 if ph > 0 else 0.0
            order.glass_height = _round_even_inch(raw_gh) if raw_gh > 0 else 0.0

            # Auto-flag reinforcement requirement
            order.reinforcement_required = w > WIDTH_104_REQUIRED

    @api.depends('extrusion_line_ids.total_weight', 'glass_type_id', 'num_panels',
                 'lites', 'glass_width', 'glass_height')
    def _compute_weight(self):
        for order in self:
            aluminum_weight = sum(line.total_weight for line in order.extrusion_line_ids)

            glass_panes = order.num_panels * max(order.lites, 1)
            glass_area_sqft = (order.glass_width * order.glass_height) / 144.0
            glass_weight = glass_area_sqft * (order.glass_type_id.weight_per_sqft or 0.0) * glass_panes

            order.door_weight = aluminum_weight + glass_weight

    @api.depends('dealer_id.dealer_markup', 'dealer_client_id.markup', 'job_markup',
                 'extrusion_line_ids.total_cost',
                 'glass_type_id.price_per_sqft', 'interlayer_id.price_per_sqft',
                 'frame_finish_id.requires_paint', 'frame_finish_id.paint_cost_per_sqft',
                 'motor_id.cost', 'misc_line_ids.total_price',
                 'num_panels', 'lites', 'glass_width', 'glass_height',
                 'frame_width', 'frame_height', 'quantity')
    def _compute_price(self):
        for order in self:
            # Markup layers:
            # 1. dealer_markup  — our markup to the dealer (set on dealer account)
            # 2. client markup  — dealer's standard markup to their client (set on client record)
            # 3. job_markup     — extra markup for this specific job
            total_markup_pct = (
                (order.dealer_id.dealer_markup or 0.0)
                + (order.dealer_client_id.markup or 0.0)
                + (order.job_markup or 0.0)
            )
            markup = 1.0 + total_markup_pct / 100.0

            # Aluminum cost
            aluminum_cost = sum(line.total_cost for line in order.extrusion_line_ids)

            # Glass + interlayer cost
            glass_panes = order.num_panels * max(order.lites, 1)
            glass_area_sqft = (order.glass_width * order.glass_height) / 144.0
            glass_cost = glass_area_sqft * (order.glass_type_id.price_per_sqft or 0.0) * glass_panes
            interlayer_cost = glass_area_sqft * (order.interlayer_id.price_per_sqft or 0.0) * glass_panes

            # Paint cost (mill finish sent to local painter — per sq ft of door face)
            paint_cost = 0.0
            if order.frame_finish_id.requires_paint:
                door_face_sqft = (order.frame_width * order.frame_height) / 144.0
                paint_cost = door_face_sqft * (order.frame_finish_id.paint_cost_per_sqft or 0.0)

            # Motor cost (markup applies)
            motor_cost = order.motor_id.cost or 0.0

            # Door unit price (markup on door + motor, not on misc)
            door_unit = (aluminum_cost + glass_cost + interlayer_cost + paint_cost + motor_cost) * markup

            # Misc items — dealer-entered sell prices, added directly (no extra markup)
            misc_total = sum(line.total_price for line in order.misc_line_ids)

            order.unit_price = door_unit + misc_total
            order.total_price = order.unit_price * (order.quantity or 1)

    # ─────────────────────────────────────────────────────────────────────────────
    # Onchange / Constraints
    # ─────────────────────────────────────────────────────────────────────────────

    @api.onchange('frame_width', 'lites')
    def _onchange_lites(self):
        if self.frame_width > MAX_WIDTH_1_LITE and self.lites == 1:
            self.lites = 2
            return {'warning': {
                'title': _('Lites adjusted'),
                'message': _('Doors wider than 12\' require a minimum of 2 lites. '
                              'Lites has been set to 2.'),
            }}

    @api.onchange('frame_width')
    def _onchange_reinforcement(self):
        if self.frame_width > WIDTH_104_REQUIRED:
            self.include_reinforcement = True

    @api.constrains('lites', 'frame_width')
    def _check_lites_width(self):
        for order in self:
            if order.frame_width > MAX_WIDTH_1_LITE and order.lites < 2:
                raise ValidationError(
                    _('Doors wider than 12\' (144") require a minimum of 2 lites.')
                )

    @api.constrains('lites')
    def _check_lites_range(self):
        for order in self:
            if not (1 <= order.lites <= 5):
                raise ValidationError(_('Lites must be between 1 and 5.'))

    # ─────────────────────────────────────────────────────────────────────────────
    # State transitions
    # ─────────────────────────────────────────────────────────────────────────────

    def action_submit(self):
        for order in self:
            if order.quote_number == 'New':
                order.quote_number = self.env['ir.sequence'].next_by_code('glass.door.quote') or '/'
            order._generate_cutting_list()
            order.state = 'submitted'

    def action_approve(self):
        for order in self:
            if order.name == 'New':
                order.name = self.env['ir.sequence'].next_by_code('glass.door.order') or '/'
            order.state = 'approved'

    def action_cutting(self):    self.write({'state': 'cutting'})
    def action_punching(self):   self.write({'state': 'punching'})
    def action_prepping(self):   self.write({'state': 'prepping'})
    def action_assembly(self):   self.write({'state': 'assembly'})
    def action_glazing(self):    self.write({'state': 'glazing'})
    def action_packing(self):    self.write({'state': 'packing'})
    def action_ready_pickup(self): self.write({'state': 'ready_pickup'})
    def action_ready_ship(self):   self.write({'state': 'ready_ship'})

    # ─────────────────────────────────────────────────────────────────────────────
    # Cutting list generation
    # ─────────────────────────────────────────────────────────────────────────────

    def _generate_cutting_list(self):
        self.ensure_one()
        self.extrusion_line_ids.unlink()

        w = self.frame_width
        h = self.frame_height
        n = self.num_panels
        l = max(self.lites, 1)
        ph = self.panel_height

        def profile(code):
            return self.env['glass.door.extrusion.profile'].search(
                [('code', '=', code)], limit=1
            )

        lines = []

        # ── 101 Top/Bottom Rim Rail ───────────────────────────────────────────
        p = profile(101)
        if p:
            lines.append({'profile_id': p.id, 'qty': 2, 'length': w,
                           'orientation': 'H', 'sequence': 10})

        # ── 102 Vertical Stiles ───────────────────────────────────────────────
        p = profile(102)
        if p:
            lines.append({'profile_id': p.id, 'qty': 2 * n, 'length': ph,
                           'orientation': 'V', 'sequence': 20})

        # ── 103 Intermediate Rail ─────────────────────────────────────────────
        if n > 1:
            p = profile(103)
            if p:
                lines.append({'profile_id': p.id, 'qty': (n * 2) - 2, 'length': w,
                               'orientation': 'H', 'sequence': 30})

        # ── 104 Internal Reinforcement (conditional) ──────────────────────────
        needs_104 = self.frame_width > WIDTH_104_REQUIRED or self.include_reinforcement
        if needs_104 and n > 1:
            p = profile(104)
            if p:
                lines.append({'profile_id': p.id, 'qty': (n * 2) - 2, 'length': w - 1.0,
                               'orientation': 'H', 'sequence': 40})

        # ── 105 Dividing Rail (lites > 1) ─────────────────────────────────────
        if l > 1:
            p = profile(105)
            if p:
                lines.append({'profile_id': p.id, 'qty': (l - 1) * n, 'length': ph,
                               'orientation': 'V', 'sequence': 50})

        # ── 106/107/108 Glass Stop (by glass thickness) ───────────────────────
        stop_code = {'5/16': 106, '7/16': 107, '13/16': 108}.get(
            self.glass_type_id.thickness
        )
        if stop_code:
            p = profile(stop_code)
            if p:
                v_len = ph - 1.374
                h_len = (w - 6.5 - 2.0 * (l - 1)) / l
                lines.append({'profile_id': p.id, 'qty': 2 * n * l, 'length': v_len,
                               'orientation': 'V', 'sequence': 60})
                lines.append({'profile_id': p.id, 'qty': 2 * n * l, 'length': h_len,
                               'orientation': 'H', 'sequence': 61})

        # ── 109 & 110 Aluminum Seal Trim (optional) ───────────────────────────
        if self.trim_type == 'aluminum':
            for seq, code in [(70, 109), (80, 110)]:
                p = profile(code)
                if p:
                    lines.append({'profile_id': p.id, 'qty': 2, 'length': h + 2.0,
                                   'orientation': 'V', 'sequence': seq})
                    lines.append({'profile_id': p.id, 'qty': 1, 'length': w + 2.0,
                                   'orientation': 'H', 'sequence': seq + 1})

        for vals in lines:
            vals['order_id'] = self.id
        self.env['glass.door.extrusion.line'].create(lines)


class GlassDoorExtrusionLine(models.Model):
    _name = 'glass.door.extrusion.line'
    _description = 'Cutting List Line'
    _order = 'sequence, id'

    order_id = fields.Many2one('glass.door.order', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    profile_id = fields.Many2one('glass.door.extrusion.profile', 'Profile', required=True)
    profile_code = fields.Integer(related='profile_id.code', store=True)
    profile_name = fields.Char(related='profile_id.name', store=True)
    qty = fields.Integer('Qty', required=True, default=1)
    length = fields.Float('Length (in)', digits=(10, 4))
    orientation = fields.Selection([('H', 'Horizontal'), ('V', 'Vertical')], string='Dir.')

    total_length = fields.Float('Total Length (in)', compute='_compute_totals', store=True,
                                 digits=(10, 4))
    total_cost = fields.Float('Cost', compute='_compute_totals', store=True, digits=(10, 4))
    total_weight = fields.Float('Weight (lbs)', compute='_compute_totals', store=True,
                                 digits=(10, 6))

    @api.depends('qty', 'length', 'profile_id.price_per_inch', 'profile_id.weight_per_inch')
    def _compute_totals(self):
        for line in self:
            tl = line.qty * line.length
            line.total_length = tl
            line.total_cost = tl * (line.profile_id.price_per_inch or 0.0)
            line.total_weight = tl * (line.profile_id.weight_per_inch or 0.0)


class GlassDoorOrderMiscLine(models.Model):
    _name = 'glass.door.order.misc.line'
    _description = 'Miscellaneous Order Item'
    _order = 'sequence, id'

    order_id = fields.Many2one('glass.door.order', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    description = fields.Char('Description', required=True)
    qty = fields.Integer('Qty', default=1, required=True)
    unit_price = fields.Float('Unit Price', digits=(10, 2),
                               help='Sell price per unit. Entered directly — no markup applied.')
    total_price = fields.Float('Total', compute='_compute_total', store=True, digits=(10, 2))

    @api.depends('qty', 'unit_price')
    def _compute_total(self):
        for line in self:
            line.total_price = (line.qty or 0) * (line.unit_price or 0.0)
