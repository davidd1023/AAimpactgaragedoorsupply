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

from odoo import api, fields, models
from odoo.tools import float_compare, float_is_zero


CABLE_WORDS = ('gac', 'sleeve', 'thimble', 'cable')


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
    is_short = fields.Boolean(string='Is Short')

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
        Line.create(values)
        return stock

    # ------------------------------------------------------------------
    # The board: orders to make, and what to order
    # ------------------------------------------------------------------

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
            'families': [{'id': f.id, 'name': f.name} for f in families],
            'orders': orders,
            'lines': [{
                'seq': l.seq,
                'product_id': l.product_id.id,
                'product': l.product_id.display_name,
                'family_id': l.family_id.id,
                'needed': l.qty_needed,
                'before': l.qty_before,
                'short': l.qty_short,
            } for l in lines],
            'products': sorted(products.values(), key=lambda p: p['name']),
        }
