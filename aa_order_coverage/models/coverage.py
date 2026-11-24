"""How far the stock on hand goes through the open orders.

Owner, 2026-11-18: every open order, oldest first, and "hasta cual me da con
el inventario que tengo" - with a filter per kind of part ("solamente de los
tracks hasta que orden me llega, o las bisagras").

THE RULE IS FIRST COME FIRST SERVED, PER PART. The stock of each part is
handed down the queue: the oldest order takes everything it needs, the next
order gets what is left, and an order that finds too little takes what there
is and is SHORT. It still takes it - it is ahead in the line - so every order
after it is short of that part too. That is what makes "up to which order"
a single answer: for any set of parts, the first short order is where the
stock runs out.

Because each part is handed out on its own, the answer for "tracks only" is
simply the same lines with everything but tracks hidden. Nothing has to be
recomputed when the family filter changes, which is why the filter can be a
plain search panel.

WHAT AN ORDER STILL NEEDS:

* the parts on its open Work Order transfer (the kit components Odoo has
  already exploded, prepared tracks, cable, sleeves...), and
* the raw materials of its open manufacturing jobs - a prepared track job
  still needs its RAW track, flag angles and jamb brackets.

A part that an open job of the SAME order is going to make (a prepared track,
the spring assembly) is not asked of the shelf twice: the job's raw materials
stand for it. Once the job is done its product is on the shelf and counts as
stock like anything else.

Springs are cut from coil by aa_spring_stock and have their own run-out
screen; a spring job carries no raw material lines here, so springs are not
part of this answer.
"""

import re
from datetime import timedelta

from odoo.exceptions import UserError
from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero


CABLE_WORDS = ('gac', 'sleeve', 'thimble', 'cable')

# 3" Vertical Track RAW - 7'4" Black   /   2" Horizontal Track RAW - 9'6" White
RAW_TRACK = re.compile(
    r"^\s*(\d)\"\s*(Vertical|Horizontal)\s+Track\s+RAW\s*-\s*(\d+)'\s*(?:(\d+)\")?\s*([\w ]+?)\s*$",
    re.I)


def raw_track_facts(product):
    """(size, kind, colour, inches) of a RAW track, or None."""
    for name in (product.name, product.with_context(display_default_code=False).display_name):
        hit = RAW_TRACK.match(name or '')
        if hit:
            return (hit.group(1), hit.group(2).lower(), hit.group(5).strip().lower(),
                    int(hit.group(3)) * 12 + int(hit.group(4) or 0))
    return None


def inches_text(inches):
    feet, rest = divmod(int(inches), 12)
    return "%d'%d\"" % (feet, rest) if rest else "%d'" % feet


class AaOrderCoverageFamily(models.Model):
    _name = 'aa.order.coverage.family'
    _description = 'Order Coverage: Part Family'
    _order = 'is_all desc, name'

    name = fields.Char(required=True)
    # ONE ROW FOR EVERYTHING, so "which orders can I complete at all" sits
    # at the top of the same screen as "how far do my tracks go".
    is_all = fields.Boolean(string='All Parts')
    line_ids = fields.One2many('aa.order.coverage.line', 'family_id')

    order_count = fields.Integer(
        string='Orders Needing It', compute='_compute_coverage')
    covered_count = fields.Integer(
        string='Orders Covered in a Row', compute='_compute_coverage',
        help='How many orders, oldest first, the stock on hand completes '
             'before the first one it cannot.')
    covered_upto = fields.Char(
        string='Covered Up To', compute='_compute_coverage',
        help='The last order covered before the stock runs out.')
    first_short = fields.Char(
        string='First Order Short', compute='_compute_coverage')
    first_short_parts = fields.Char(
        string='Short Of', compute='_compute_coverage',
        help='What the first short order is missing, and how many.')
    short_order_count = fields.Integer(
        string='Orders Short', compute='_compute_coverage')

    _name_unique = models.Constraint('UNIQUE(name)', 'One family per name.')

    @api.depends_context('uid')
    def _compute_coverage(self):
        Line = self.env['aa.order.coverage.line']
        mine = Line.search([('user_id', '=', self.env.uid)])
        for family in self:
            lines = mine if family.is_all else mine.filtered(
                lambda l, f=family: l.family_id == f)
            orders = {}
            for line in lines:
                info = orders.setdefault(line.seq, {
                    'label': line.order_label, 'short': []})
                if line.is_short:
                    info['short'].append(line)
            seqs = sorted(orders)
            covered = []
            first = None
            for seq in seqs:
                if orders[seq]['short']:
                    first = seq
                    break
                covered.append(seq)
            family.order_count = len(seqs)
            family.covered_count = len(covered)
            family.covered_upto = orders[covered[-1]]['label'] if covered else False
            family.short_order_count = sum(1 for s in seqs if orders[s]['short'])
            if first is None:
                family.first_short = False
                family.first_short_parts = False
            else:
                family.first_short = orders[first]['label']
                family.first_short_parts = ', '.join(
                    '%s (short %g)' % (l.product_id.display_name, l.qty_short)
                    for l in orders[first]['short'])

    def action_open_lines(self):
        """The orders behind one row, with only this family's parts."""
        self.ensure_one()
        action = self.env['aa.order.coverage.line']._aa_lines_action()
        if not self.is_all:
            action['domain'] = action['domain'] + [('family_id', '=', self.id)]
            action['name'] = 'Order Coverage: %s' % self.name
        return action


class AaOrderCoverageLine(models.Model):
    _name = 'aa.order.coverage.line'
    _description = 'Order Coverage: What an Order Still Needs'
    _order = 'seq, family_id, product_id'

    # PER USER, so two people opening the screen at once do not wipe each
    # other's figures mid-read. A record rule keeps each to his own.
    user_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user)

    seq = fields.Integer(string='#', help='Place in the queue, oldest first.')
    # THE GROUP KEY. Zero-padded place first, so grouping by it keeps the
    # queue in order in the list AND as the rows of the pivot.
    order_label = fields.Char(string='Order', index=True)
    picking_id = fields.Many2one(
        'stock.picking', string='Work Order', ondelete='cascade')
    sale_id = fields.Many2one('sale.order', string='Sale Order')
    wo_number = fields.Char(string='W/O #')
    po_number = fields.Char(string='PO Number')
    partner_id = fields.Many2one('res.partner', string='Customer')
    pickup_date = fields.Date(string='Pickup Day')

    product_id = fields.Many2one('product.product', string='Part', index=True)
    family_id = fields.Many2one(
        'aa.order.coverage.family', string='Family', index=True)
    uom_id = fields.Many2one('uom.uom', string='Unit')
    source = fields.Selection([
        ('order', 'Goes out with the order'),
        ('prep', 'Used to prepare it'),
    ], string='Needed For')

    qty_needed = fields.Float(string='Needs', digits='Product Unit')
    qty_before = fields.Float(
        string='Left When Its Turn Came', digits='Product Unit',
        help='Stock still free once every older order took its share.')
    qty_short = fields.Float(string='Short', digits='Product Unit')
    is_short = fields.Boolean(
        string='Is Short',
        help='Short even after cutting it from a longer track.')
    # CUT IT FROM A LONGER TRACK (owner, 2026-11-18): "cuando se nos acabe
    # algun track de cierta medida y haya alguno mas grande, que nos diga que
    # es posible fabricarlo pero usando un track de x medida".
    swap_product_id = fields.Many2one(
        'product.product', string='Cut From',
        help='A longer RAW track of the same size, kind and colour that is '
             'left over after every open order took its own.')
    qty_swap = fields.Float(
        string='Cut From Longer', digits='Product Unit',
        help='How many of the short pieces the longer track covers.')
    # PAINT A GALVANIZED ONE (owner, 2026-11-19): "si hay algun material mill
    # finish que podamos pintar y terminar ordenes ... aqui quiero ver que me
    # diga eso". Mill Finish and Galvanized are the same thing.
    paint_product_id = fields.Many2one(
        'product.product', string='Paint From',
        help='The same part in Galvanized, spare after every open order took '
             'its own and after what is already at the painter.')
    qty_paint = fields.Float(
        string='Paint From Galvanized', digits='Product Unit',
        help='How many of the missing pieces a painted Galvanized one covers.')

    # ------------------------------------------------------------------
    # The menu
    # ------------------------------------------------------------------

    @api.model
    def action_open_coverage(self):
        """Work the figures out afresh and open them."""
        # SUDO TO READ, NOT TO SHOW: the figures need sale orders and
        # manufacturing jobs a warehouse clerk may not open, while the lines
        # written still belong to whoever opened the screen (sudo keeps uid).
        self.sudo()._aa_rebuild()
        return self._aa_lines_action()

    @api.model
    def action_open_families(self):
        self.sudo()._aa_rebuild()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'aa_order_coverage.action_aa_coverage_family')
        # Only the families some open order actually needs.
        action['domain'] = ['|', ('is_all', '=', True),
                            ('line_ids.user_id', '=', self.env.uid)]
        return action

    @api.model
    def _aa_lines_action(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'aa_order_coverage.action_aa_coverage_lines')
        action['domain'] = [('user_id', '=', self.env.uid)]
        return action

    # ------------------------------------------------------------------
    # The arithmetic
    # ------------------------------------------------------------------

    @api.model
    def _aa_open_orders(self):
        """Open Work Order transfers, oldest order first."""
        types = self.env['stock.warehouse'].search([]).mapped('pick_type_id')
        pickings = self.env['stock.picking'].search([
            ('picking_type_id', 'in', types.ids),
            ('state', 'not in', ('done', 'cancel')),
        ])
        orders = {p: self._aa_sale_order(p) for p in pickings}

        def queue_key(picking):
            so = orders[picking]
            when = (so and so.date_order) or picking.create_date
            return (when, picking.id)

        return [(p, orders[p]) for p in pickings.sorted(queue_key)]

    # The note work_order_sheet leaves when the last station finishes but the
    # Work Order cannot go to Dispatch yet (something is not in stock).
    STATIONS_DONE_NOTE = 'All stations are done'

    @api.model
    def _aa_through_shop_floor(self, queue):
        """The Work Orders that have already been through the Shop Floor.

        Owner, 2026-11-18: "las ordenes que ya pasaron por el shop floor no
        deben salir aca, por ejemplo 942". Such an order is made - it is
        waiting at Dispatch for paperwork, not for the shop. It counts when
        every manufacturing job of the order is done, OR Odoo recorded on its
        Work Order that all stations were done: W/O #344 (942) finished on
        10 Nov and jobs created for it on 11 Nov would otherwise put it back.
        """
        done = set()
        pickings = self.env['stock.picking'].browse([p.id for p, _so in queue])
        if not pickings:
            return done
        noted = set(self.env['mail.message'].sudo().search([
            ('model', '=', 'stock.picking'),
            ('res_id', 'in', pickings.ids),
            ('body', 'ilike', self.STATIONS_DONE_NOTE),
        ]).mapped('res_id'))
        Production = self.env['mrp.production'].sudo()
        for picking, so in queue:
            if picking.id in noted:
                done.add(picking.id)
                continue
            if not so:
                continue
            jobs = Production.search([('origin', '=', so.name), ('state', '!=', 'cancel')])
            if jobs and all(j.state == 'done' for j in jobs):
                done.add(picking.id)
        return done

    @api.model
    def _aa_sale_order(self, picking):
        if picking.sale_id:
            return picking.sale_id
        if picking.origin:
            return self.env['sale.order'].search(
                [('name', '=', picking.origin)], limit=1)
        return self.env['sale.order']

    @api.model
    def _aa_open_jobs(self, sale_order):
        if not sale_order:
            return self.env['mrp.production']
        return self.env['mrp.production'].search([
            ('origin', '=', sale_order.name),
            ('state', 'not in', ('done', 'cancel')),
        ])

    @api.model
    def _aa_needs(self, picking, sale_order):
        """{product: (qty in product unit, source)} still to come off the shelf."""
        needs = {}

        def add(product, qty, source):
            if not product.is_storable or float_is_zero(
                    qty, precision_rounding=product.uom_id.rounding):
                return
            have, src = needs.get(product, (0.0, source))
            # A part both prepared with and sent out counts as "prep":
            # it is wanted at a bench first.
            needs[product] = (have + qty, 'prep' if 'prep' in (src, source) else source)

        made_here = {}
        for job in self._aa_open_jobs(sale_order):
            made_here[job.product_id] = made_here.get(job.product_id, 0.0) + \
                job.product_uom_id._compute_quantity(
                    job.product_qty, job.product_id.uom_id)
            for move in job.move_raw_ids:
                if move.state in ('done', 'cancel'):
                    continue
                add(move.product_id, move.product_qty, 'prep')

        for move in picking.move_ids:
            if move.state in ('done', 'cancel'):
                continue
            qty = move.product_qty
            # MADE BY THIS ORDER'S OWN JOB: its raw materials are already
            # counted above, so the finished part is not asked of the shelf.
            made = made_here.get(move.product_id, 0.0)
            if made:
                used = min(made, qty)
                made_here[move.product_id] = made - used
                qty -= used
            add(move.product_id, qty, 'order')
        return needs

    @api.model
    def _aa_on_hand(self, pickings):
        """Free-standing stock per product in the locations orders draw from."""
        locations = pickings.mapped('location_id')
        if not locations:
            return {}
        groups = self.env['stock.quant']._read_group(
            [('location_id', 'child_of', locations.ids),
             ('location_id.usage', '=', 'internal')],
            ['product_id'], ['quantity:sum'])
        return {product: qty for product, qty in groups}

    @api.model
    def _aa_family(self, product, cache):
        name = product.categ_id.name if product.categ_id else ''
        if not name or name in ('All', 'Goods', 'Saleable'):
            lower = (product.name or '').lower()
            if any(word in lower for word in CABLE_WORDS):
                name = 'Cables'
            elif not name:
                name = 'Other'
        if name not in cache:
            Family = self.env['aa.order.coverage.family'].sudo()
            cache[name] = Family.search([('name', '=', name)], limit=1) or \
                Family.create({'name': name})
        return cache[name]

    @api.model
    def _aa_rebuild(self):
        Line = self.sudo()
        Line.search([('user_id', '=', self.env.uid)]).unlink()

        queue = self._aa_open_orders()
        pickings = self.env['stock.picking'].browse([p.id for p, _so in queue])
        stock = self._aa_on_hand(pickings)
        # ALREADY THROUGH THE SHOP FLOOR: not shown, but what goes out with
        # them is in their boxes and still on the books, so it comes off the
        # shelf FIRST - nobody else can count on it.
        finished = self._aa_through_shop_floor(queue)
        for picking, _so in queue:
            if picking.id not in finished:
                continue
            for move in picking.move_ids:
                if move.state in ('done', 'cancel') or not move.product_id.is_storable:
                    continue
                stock[move.product_id] = stock.get(move.product_id, 0.0) - move.product_qty
        queue = [(p, so) for p, so in queue if p.id not in finished]
        left = dict(stock)
        families = {}
        values = []
        for seq, (picking, so) in enumerate(queue, start=1):
            wo = picking.aa_wo_number if 'aa_wo_number' in picking._fields else False
            wo = wo or picking.name
            po = (picking.aa_po_number if 'aa_po_number' in picking._fields else False) \
                or (so and so.client_order_ref) or False
            pickup = picking.aa_pickup_date if 'aa_pickup_date' in picking._fields else False
            label = '%04d · %s · %s' % (seq, wo, po or (so and so.name) or picking.origin or '')
            needs = self._aa_needs(picking, so)
            for product in sorted(needs, key=lambda p: p.display_name or ''):
                qty, source = needs[product]
                before = left.get(product, 0.0)
                rounding = product.uom_id.rounding
                covered = min(qty, max(before, 0.0))
                short = qty - covered
                left[product] = before - qty
                values.append({
                    'user_id': self.env.uid,
                    'seq': seq,
                    'order_label': label,
                    'picking_id': picking.id,
                    'sale_id': so.id if so else False,
                    'wo_number': wo,
                    'po_number': po,
                    'partner_id': picking.partner_id.id,
                    'pickup_date': pickup,
                    'product_id': product.id,
                    'family_id': self._aa_family(product, families).id,
                    'uom_id': product.uom_id.id,
                    'source': source,
                    'qty_needed': qty,
                    'qty_before': max(before, 0.0),
                    'qty_short': short if float_compare(
                        short, 0.0, precision_rounding=rounding) > 0 else 0.0,
                    'is_short': float_compare(
                        short, 0.0, precision_rounding=rounding) > 0,
                })
        self._aa_cut_from_longer(values, stock)
        self._aa_use_other_flag(values, stock)
        self._aa_paint_from_galvanized(values, stock)
        Line.create(values)
        return stock

    @api.model
    def _aa_cut_from_longer(self, values, stock):
        """Cover a short RAW track with a LONGER one of the same size, kind
        and colour (owner, 2026-11-18).

        ONLY WHAT IS SPARE: a longer piece counts only once every open order
        that needs THAT length has had its own, so cutting one never leaves
        another order short. The spare goes to the oldest short order first,
        shortest piece that fits first (less is thrown away - the offcut is
        discarded). One longer piece makes one shorter piece.
        """
        Product = self.env['product.product']
        tracks = {}
        demand = {}
        for v in values:
            demand[v['product_id']] = demand.get(v['product_id'], 0.0) + v['qty_needed']
        for product, qty in stock.items():
            facts = raw_track_facts(product)
            if facts:
                tracks[product.id] = facts
        for pid in demand:
            if pid not in tracks:
                facts = raw_track_facts(Product.browse(pid))
                if facts:
                    tracks[pid] = facts
        spare = {}
        for pid in tracks:
            free = max(stock.get(Product.browse(pid), 0.0), 0.0) - demand.get(pid, 0.0)
            if free >= 1:
                spare[pid] = float(int(free + 1e-6))  # whole pieces
        for v in values:
            if not v['is_short'] or v['product_id'] not in tracks:
                continue
            size, kind, colour, inches = tracks[v['product_id']]
            fits = sorted(
                (tracks[pid][3], pid) for pid, free in spare.items()
                if free > 0 and tracks[pid][:3] == (size, kind, colour)
                and tracks[pid][3] > inches)
            if not fits:
                continue
            pid = fits[0][1]
            take = min(spare[pid], float(int(v['qty_short'] + 1 - 1e-6)))
            spare[pid] -= take
            v['swap_product_id'] = pid
            v['qty_swap'] = take
            v['is_short'] = v['qty_short'] - take > 1e-6

    @api.model
    def _aa_flag_facts(self, product):
        """(template id, colour) of a Flag Angle variant, or None."""
        if 'flag angle' not in (product.name or '').lower():
            return None
        colour = product.product_template_attribute_value_ids.filtered(
            lambda v: (v.attribute_id.name or '').strip().lower()
            in ('colour', 'color', 'finish color', 'finish colour'))[:1]
        return (product.product_tmpl_id.id, (colour.name or '').strip().lower())

    @api.model
    def _aa_use_other_flag(self, values, stock):
        """Out of one flag angle, use the OTHER size in the same colour
        (owner, 2026-11-20: "puedes usar el otro flag" - 5.9" for a 3" track
        when the 6-3/8" runs out, and the other way round).

        ONLY WHAT IS SPARE, oldest order first, the same rule as cutting a
        longer track: the other size counts once every open order that needs
        IT has had its own. Shown on the line as the part to use instead.
        """
        Product = self.env['product.product'].sudo()
        demand = {}
        for v in values:
            demand[v['product_id']] = demand.get(v['product_id'], 0.0) + v['qty_needed']
        facts, spare = {}, {}
        for v in values:
            if not v['is_short'] or v.get('qty_swap'):
                continue
            pid = v['product_id']
            if pid not in facts:
                facts[pid] = self._aa_flag_facts(Product.browse(pid))
            mine = facts[pid]
            if not mine:
                continue
            others = Product.browse(pid).product_tmpl_id.product_variant_ids.filtered(
                lambda p: p.id != pid and self._aa_flag_facts(p) == mine)
            for other in others:
                if other.id not in spare:
                    spare[other.id] = float(int(max(
                        max(stock.get(other, 0.0), 0.0) - demand.get(other.id, 0.0), 0.0) + 1e-6))
            pick = next((o for o in others if spare.get(o.id, 0) > 0), None)
            if not pick:
                continue
            take = min(spare[pick.id], float(int(v['qty_short'] + 1 - 1e-6)))
            spare[pick.id] -= take
            v['swap_product_id'] = pick.id
            v['qty_swap'] = take
            v['is_short'] = v['qty_short'] - take > 1e-6

    # ------------------------------------------------------------------
    # The board: orders to make, and what to order
    # ------------------------------------------------------------------

    @api.model
    def _aa_paint_lines(self):
        """Open purchase lines to a painter, not yet received - drafts too,
        since the Galvanized parts are spoken for once the P.O. is written."""
        return self.env['purchase.order.line'].sudo().search([
            ('order_id.state', 'in', ('draft', 'sent', 'to approve', 'purchase')),
            '|', ('order_id.partner_id.aa_paints_parts', '=', True),
            ('order_id.partner_id.commercial_partner_id.aa_paints_parts', '=', True),
            ('display_type', '=', False),
        ]).filtered(lambda l: l.product_qty > l.qty_received)

    @api.model
    def _aa_paint_from_galvanized(self, values, stock):
        """Cover what is still missing with a Galvanized twin, painted.

        AFTER CUTTING FROM A LONGER TRACK, which is immediate; painting takes
        a trip to the painter, so the line stays short - its date comes from
        the paint P.O. once there is one.

        ONLY WHAT IS SPARE, as with the longer tracks: a Galvanized part counts
        once every open order that needs it Galvanized has had its own, and
        once what already sits on a paint P.O. is set aside for that P.O.

        WHAT IS ALREADY AT THE PAINTER COVERS FIRST: a paint P.O. for the
        coloured part goes to the oldest short orders, so the same part is
        not suggested twice.
        """
        from .paint import galvanized_twin
        Product = self.env['product.product'].sudo()
        cache = {}
        demand = {}
        for v in values:
            demand[v['product_id']] = demand.get(v['product_id'], 0.0) + v['qty_needed']
        painting = {}   # coloured product id -> qty already on a paint P.O.
        promised = {}   # twin id -> qty already going to the painter
        for line in self._aa_paint_lines():
            qty = line.product_uom_id._compute_quantity(
                line.product_qty - line.qty_received, line.product_id.uom_id)
            painting[line.product_id.id] = painting.get(line.product_id.id, 0.0) + qty
            twin = galvanized_twin(line.product_id, cache)
            if twin:
                promised[twin.id] = promised.get(twin.id, 0.0) + qty
        spare = {}
        for v in values:
            remaining = v['qty_short'] - v.get('qty_swap', 0.0)
            if remaining <= 1e-6:
                continue
            pid = v['product_id']
            if painting.get(pid, 0.0) > 0:
                took = min(painting[pid], remaining)
                painting[pid] -= took
                remaining -= took
                if remaining <= 1e-6:
                    continue
            twin = galvanized_twin(Product.browse(pid), cache)
            if not twin:
                continue
            if twin.id not in spare:
                spare[twin.id] = float(int(
                    max(stock.get(twin, 0.0), 0.0) - demand.get(twin.id, 0.0)
                    - promised.get(twin.id, 0.0) + 1e-6))
            take = min(spare[twin.id], float(int(remaining + 1 - 1e-6)))
            if take <= 0:
                continue
            spare[twin.id] -= take
            v['paint_product_id'] = twin.id
            v['qty_paint'] = take

    @api.model
    def aa_paint_po(self, product_id, qty, vendor_id=False):
        """A draft paint P.O. for a coloured part, opened for the date to be
        set - the date the painted parts are picked up is the expected
        arrival, and confirming it is what puts it on Orders to Make."""
        from .paint import galvanized_twin
        if not self.env.user.has_group('purchase.group_purchase_user') and \
                not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_('Only purchasing or an inventory manager can create a paint P.O.'))
        product = self.env['product.product'].browse(int(product_id)).exists()
        if not product:
            raise UserError(_('That part no longer exists.'))
        twin = galvanized_twin(product)
        Partner = self.env['res.partner'].sudo()
        painter = Partner.browse(int(vendor_id)).exists() if vendor_id else \
            Partner.search([('aa_paints_parts', '=', True)], order='name', limit=1)
        if not painter:
            raise UserError(_('Add a painter first: Orders to Make > Settings > Painters.'))
        name = _('Paint %(part)s from %(twin)s', part=product.display_name,
                 twin=twin.display_name if twin else _('Galvanized'))
        order = self.env['purchase.order'].create({
            'partner_id': painter.id,
            'origin': _('Paint (Orders to Make)'),
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': name,
                'product_qty': max(float(qty or 0), 1.0),
            })],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': order.id,
            'views': [[False, 'form']],
            'target': 'current',
        }

    @api.model
    def _aa_arrivals(self, products):
        """{product: [(date, qty, P.O. name)]} still to arrive on CONFIRMED
        purchase orders, earliest first. A draft is not counted: nothing is
        coming until somebody has actually sent the order."""
        arrivals = {}
        if not products:
            return arrivals
        PoLine = self.env['purchase.order.line'].sudo()
        for line in PoLine.search([
                ('product_id', 'in', products.ids),
                ('order_id.state', '=', 'purchase'),
                ('display_type', '=', False)]):
            left = line.product_qty - line.qty_received
            if left <= 0:
                continue
            qty = line.product_uom_id._compute_quantity(left, line.product_id.uom_id)
            when = (line.date_planned or line.order_id.date_planned)
            arrivals.setdefault(line.product_id, []).append(
                (when.date() if when else False, qty, line.order_id.name))
        for rows in arrivals.values():
            rows.sort(key=lambda r: (r[0] or fields.Date.today(), r[2]))
        return arrivals

    @api.model
    def _aa_lines_with_arrivals(self, lines, stock):
        """Each line, and - when it is short - the P.O. that covers it.

        Owner, 2026-11-18: click an order and see what is missing, whether a
        P.O. is on its way and when it lands, and roughly when the order
        could be finished. FIRST COME FIRST SERVED CARRIES ON PAST THE SHELF:
        an arriving P.O. covers the oldest short order first, so a line is
        covered on the day the shelf PLUS everything arrived by then reaches
        all the demand up to and including this order.
        """
        # BOTH FLAG ANGLE SIZES OF ONE COLOUR ARE ONE POOL (owner,
        # 2026-11-24): P00009 brought the 5.9" only, and every order wanting
        # a 6-3/8" read "not ordered" while 365 Black and 35 Galvanized 5.9"
        # were on their way. The shop uses either size, so the shelf, the
        # demand and the arrivals of the two are counted together - first
        # come first served over the pair, exactly as for one part.
        products = lines.mapped('product_id')
        pool_of, members = {}, {}
        for product in products:
            facts = self._aa_flag_facts(product)
            if not facts:
                continue
            pool_of[product] = ('flag',) + facts
            for twin in product.product_tmpl_id.product_variant_ids:
                if twin != product and self._aa_flag_facts(twin) == facts:
                    pool_of.setdefault(twin, ('flag',) + facts)
        for product, key in pool_of.items():
            members.setdefault(key, self.env['product.product'])
            members[key] |= product
        wanted = products
        for group in members.values():
            wanted |= group
        arrivals = self._aa_arrivals(wanted)
        pooled_arrivals, pooled_stock = {}, {}
        for key, group in members.items():
            rows = []
            for member in group:
                label = member.with_context(display_default_code=False).display_name
                rows += [(w, q, n, label) for w, q, n in arrivals.get(member, [])]
            rows.sort(key=lambda r: (r[0] or fields.Date.today(), r[2]))
            pooled_arrivals[key] = rows
            pooled_stock[key] = sum(max(stock.get(m, 0.0), 0.0) for m in group)
        demand = {}
        out = []
        for l in lines:
            product = l.product_id
            key = pool_of.get(product, product)
            demand[key] = demand.get(key, 0.0) + l.qty_needed
            eta = po = po_part = ''
            if key in pooled_arrivals:
                mine = product.with_context(display_default_code=False).display_name
                coming = [(w, q, n if part == mine else '%s (%s)' % (n, part))
                          for w, q, n, part in pooled_arrivals[key]]
                parts = [part if part != mine else ''
                         for _w, _q, _n, part in pooled_arrivals[key]]
                shelf = pooled_stock[key]
            else:
                coming = arrivals.get(product, [])
                parts = [''] * len(coming)
                shelf = max(stock.get(product, 0.0), 0.0)
            if l.is_short:
                still = demand[key] - shelf
                got = 0.0
                # THE OTHER FLAG SIZE IS WHAT ARRIVES: `po_part` says so, so
                # the screen reads "use the 5.9\" when it comes", not "missing".
                for (when, qty, name), part in zip(coming, parts):
                    got += qty
                    if got >= still - 1e-6:
                        eta = fields.Date.to_string(when) if when else ''
                        po = name.split(' (', 1)[0] if part else name
                        po_part = part
                        break
            out.append({
                'seq': l.seq,
                'product_id': product.id,
                'product': product.display_name,
                'family_id': l.family_id.id,
                'needed': l.qty_needed,
                'before': l.qty_before,
                # SHORT AFTER CUTTING FROM A LONGER TRACK: what holds the order back.
                'short': max(l.qty_short - l.qty_swap, 0.0) if l.is_short else 0.0,
                'missing': l.qty_short,
                'swap': l.swap_product_id.with_context(
                    display_default_code=False).display_name if l.swap_product_id else '',
                'swap_qty': l.qty_swap,
                'swap_length': inches_text(raw_track_facts(l.swap_product_id)[3])
                if l.swap_product_id and raw_track_facts(l.swap_product_id) else '',
                'paint': l.paint_product_id.with_context(
                    display_default_code=False).display_name if l.paint_product_id else '',
                'paint_qty': l.qty_paint,
                'eta': eta,
                'po': po,
                'po_part': po_part,
                'coming': [{'date': fields.Date.to_string(w) if w else '',
                            'qty': q, 'po': n} for w, q, n in coming],
            })
        return out

    # ------------------------------------------------------------------
    # How much work is left, and how much the shop does in a day
    # ------------------------------------------------------------------

    CAPACITY_DEFAULTS = {'tracks': 6, 'boxes': 10, 'springs': 20}

    @api.model
    def _aa_capacity(self):
        """Owner, 2026-11-18: "hacemos 6-9 tracks al dia, y 10 a 15 cajas de
        hardware con sus muelles". The LOW end is the default, because a date
        that is met beats one that is not; both are settings, changed on the
        screen."""
        ICP = self.env['ir.config_parameter'].sudo()
        out = {}
        for key, default in self.CAPACITY_DEFAULTS.items():
            try:
                value = float(ICP.get_param('aa_order_coverage.per_day_%s' % key) or default)
            except ValueError:
                value = default
            out[key] = value if value > 0 else default
        return out

    # Owner, 2026-11-18: "nosotros empezamos enero 4 a trabajar", closed
    # from the 24th of December. One date or a FROM..TO range per line; a
    # line that does not read as a date is ignored rather than raising,
    # the same call as the pickup holidays. Unset means this shutdown;
    # saved empty means no closed days at all.
    CLOSED_DEFAULT = '2026-12-24..2027-01-03'

    @api.model
    def _aa_closed_text(self):
        value = self.env['ir.config_parameter'].sudo().get_param('aa_order_coverage.closed_days')
        return self.CLOSED_DEFAULT if value is False or value is None else value

    @api.model
    def _aa_closed_days(self, text=None):
        """Every closed date, as ISO strings, sorted."""
        text = self._aa_closed_text() if text is None else text
        out = set()
        for raw in (text or '').replace(',', '\n').splitlines():
            raw = raw.strip()
            if not raw:
                continue
            start, _sep, end = raw.partition('..')
            try:
                first = fields.Date.to_date(start.strip())
                last = fields.Date.to_date(end.strip()) if end.strip() else first
            except ValueError:
                continue
            if not first or not last or last < first or (last - first).days > 366:
                continue
            day = first
            while day <= last:
                out.add(day.isoformat())
                day += timedelta(days=1)
        return sorted(out)

    @api.model
    def aa_set_closed_days(self, text):
        if not self.env.su and not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Only an inventory manager can change the shop's closed days."))
        self.env['ir.config_parameter'].sudo().set_param(
            'aa_order_coverage.closed_days', (text or '').strip() or ' ')
        return self._aa_closed_days()

    @api.model
    def aa_set_capacity(self, tracks, boxes, springs=None):
        if not self.env.su and not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Only an inventory manager can change the shop's daily capacity."))
        ICP = self.env['ir.config_parameter'].sudo()
        pairs = [('tracks', tracks), ('boxes', boxes)]
        if springs is not None:
            pairs.append(('springs', springs))
        for key, value in pairs:
            value = float(value or 0)
            if value <= 0:
                raise UserError(_("A daily capacity must be more than nothing."))
            ICP.set_param('aa_order_coverage.per_day_%s' % key, value)
        return self._aa_capacity()

    @api.model
    def _aa_work_left(self, sale_order):
        """Tracks and boxes this order still has to go through the shop.

        A TRACK IS ONE DOOR'S SET: the prepared-track jobs come one per
        horizontal and one per vertical, each in the number of doors, so a
        door's tracks are the larger of the two counts, not their sum.
        A BOX is a hardware kit job. SPRINGS are their own bench (owner,
        2026-11-18, the settings asked for tracks, boxes AND springs a day),
        counted one per spring on the spring jobs.
        """
        jobs = self.sudo()._aa_open_jobs(sale_order)
        horizontal = vertical = other = boxes = springs = 0.0
        for job in jobs:
            kind = job.aa_station_kind if 'aa_station_kind' in job._fields else False
            qty = job.product_qty
            if kind == 'kit':
                boxes += qty
            elif kind == 'spring':
                springs += qty
            elif kind == 'cable':
                continue
            else:
                name = (job.product_id.name or '').lower()
                if 'track' not in name and kind != 'track':
                    continue
                if 'vertical' in name:
                    vertical += qty
                elif 'horizontal' in name:
                    horizontal += qty
                else:
                    other += qty
        tracks = max(horizontal, vertical) + other
        return {'tracks': tracks, 'boxes': boxes, 'springs': springs}

    @api.model
    def aa_board_data(self):
        """Everything the Orders to Make screen draws, in one call.

        Owner, 2026-11-18: "quiero ver las ordenes por hacer y que me salgan
        segun los filtros que ponga, que podemos hacer y que falta por pedir"
        - and "por pedir me refiero a que no tengamos".

        The screen decides "can we make it" in the browser from these lines,
        for whichever families are ticked, because each part is handed out
        on its own (see the module docstring): an order can be made for a set
        of families exactly when none of its lines in those families is
        short. So ticking a box needs no round trip.
        """
        stock = self.sudo()._aa_rebuild()
        lines = self.search([('user_id', '=', self.env.uid)])
        orders, seen = [], set()
        for line in lines:
            if line.seq in seen:
                continue
            seen.add(line.seq)
            orders.append({
                'seq': line.seq,
                'wo': line.wo_number or '',
                'po': line.po_number or '',
                'customer': line.partner_id.display_name or '',
                'pickup': fields.Date.to_string(line.pickup_date) if line.pickup_date else '',
                'picking_id': line.picking_id.id,
                **self._aa_work_left(line.sale_id),
            })
        products = {}
        for line in lines:
            info = products.setdefault(line.product_id.id, {
                'id': line.product_id.id,
                'name': line.product_id.display_name,
                'family_id': line.family_id.id,
                'uom': line.uom_id.name or '',
                'needed': 0.0,
                'orders': 0,
            })
            info['needed'] += line.qty_needed
            info['orders'] += 1
        Product = self.env['product.product'].sudo()
        for pid, info in products.items():
            product = Product.browse(pid)
            on_hand = stock.get(product, 0.0)
            info['on_hand'] = on_hand
            # WHAT WE DO NOT HAVE: everything the open orders want, less the
            # shelf. Incoming purchases are shown beside it, not taken off,
            # so it is plain what is already on its way.
            info['missing'] = max(info['needed'] - max(on_hand, 0.0), 0.0)
            info['incoming'] = product.incoming_qty
            info['to_order'] = max(info['missing'] - product.incoming_qty, 0.0)
            seller = product.seller_ids[:1]
            info['vendor'] = seller.partner_id.display_name if seller else ''
        # THE NEXT P.O.: what each vendor should be sent, from the open
        # orders above plus the pace parts have been used at.
        open_needs = {Product.browse(pid): info['needed'] for pid, info in products.items()}
        cache = {}
        next_po = self.env['aa.next.po'].sudo().aa_next_po(
            open_needs, lambda product: self._aa_family(product, cache))
        family_ids = set(lines.mapped('family_id').ids)
        for vendor in next_po['vendors']:
            family_ids.update(row['family_id'] for row in vendor['lines'])
        family_ids.update(row['family_id'] for row in next_po['no_vendor'])
        families = self.env['aa.order.coverage.family'].search(
            [('is_all', '=', False), ('id', 'in', list(family_ids))])
        return {
            'next_po': next_po,
            'capacity': self._aa_capacity(),
            'closed_days': self._aa_closed_days(),
            'families': [{'id': f.id, 'name': f.name} for f in families],
            'orders': orders,
            'lines': self._aa_lines_with_arrivals(lines, stock),
            'products': sorted(products.values(), key=lambda p: p['name']),
        }
