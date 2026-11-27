"""ONE DOOR, ONE HARDWARE LINE: CHI or ATL (owner, 2026-11-25).

"yo no puedo mesclar hinges de chi con jamb brackets de ATL" - and when asked
which parts have to come from the same line: "Jamb brackets, hinges, bottom
bracket". Everything else (springs, cones, cable, drums, shafts, tracks,
screws) goes with either.

THE PRODUCT SAYS WHICH LINE IT IS. `aa_hw_line` on the template - CHI, ATL,
or blank for a part that fits both. `aa_line_must_match` marks the three kinds
that must agree on one door. `aa_line_twin_id` is the same part from the other
line: the ATL Jamb Bracket's twin is the CHI Jamb Bracket, and a variant's twin
is the twin template's variant with the same values (size, colour, hand).

WHICH LINE GOES FIRST: "CHI le damos prioridad cuando es powder coated
hardware, pero cuando es mill finish da lo mismo usar uno que el otro segun el
inventario". So Orders to Make suggests the other line only when the door's
own line is short and the other covers EVERY must-match part of the order; and
a powder-coated order sitting on ATL is offered CHI back as soon as CHI covers
it.

THE SWITCH IS ONE BUTTON AND IT CHANGES THE PICK LIST, not a note beside it:
`sale.order.aa_set_hw_line` swaps the must-match parts on the order's open
transfers and on the open jobs (a vertical track job holds the jamb brackets)
for their twins. The kit stays the kit and keeps its BoM line on every move,
which is what Odoo counts a kit's delivered quantity by, so the order still
reads as delivered when it goes out.

THE ATL HORIZONTAL COMES WITHOUT ITS 2x2 ANGLE ("el horizontal lleva el
producto 2 x 2 atornillado a el, cuando el de chi ya trae el 2x2"). A RAW part
can name what is bolted on when it is prepared (`aa_prep_part_id`) and the
Track Prep card says so; a job that is switched to it gets that part added to
its components.
"""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LINES = [('chi', 'CHI'), ('atl', 'ATL')]
LINE_NAMES = dict(LINES)

# THE LINE CAN BE A VARIANT CHOICE (owner, 2026-11-27): the RAW tracks were
# folded into one product per size and type with ATL kept "dentro del mismo
# producto", so a RAW piece says its line in a value of this attribute rather
# than on its template. Read by name, because spring_engineering - which
# creates the attribute - is not a dependency of this module.
LINE_ATTRIBUTES = ('line', 'hardware line')


def _line_value(product):
    """The product's Line value (a product.template.attribute.value), or empty."""
    return product.product_template_attribute_value_ids.filtered(
        lambda v: (v.attribute_id.name or '').strip().lower() in LINE_ATTRIBUTES
        and (v.name or '').strip().lower() in LINE_NAMES)[:1]


def _names(product):
    return {(v.name or '').strip().lower()
            for v in product.product_template_attribute_value_ids}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    aa_hw_line = fields.Selection(
        LINES, string='Hardware Line',
        help='Which hardware line this part belongs to. Blank: it fits a door '
             'of either line.')
    aa_line_must_match = fields.Boolean(
        string='Must Match the Door',
        help='Jamb brackets, hinges and bottom brackets: every one on a door '
             'comes from the same line, CHI or ATL.')
    aa_line_twin_id = fields.Many2one(
        'product.template', string='Same Part, Other Line',
        help='The same part from the other hardware line. Variants are paired '
             'by their values (size, colour, hand).')
    aa_prep_part_id = fields.Many2one(
        'product.product', string='Add When Preparing',
        help='A part bolted on at Track Prep because this one comes without '
             'it - the 2x2 angle on an ATL horizontal.')
    aa_prep_part_qty = fields.Float(
        string='Per Piece', default=1.0, digits='Product Unit')
    aa_prep_note = fields.Char(
        string='Preparation Note',
        help='Printed on the Track Prep card whenever this part is used.')

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates.filtered('aa_line_twin_id')._aa_pair_back()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if vals.get('aa_line_twin_id'):
            self._aa_pair_back()
        return res

    def _aa_pair_back(self):
        # BOTH WAYS ROUND: pairing the ATL part with the CHI one pairs the
        # CHI one back, unless it is already paired with something else.
        for template in self:
            twin = template.aa_line_twin_id
            if twin and not twin.aa_line_twin_id:
                twin.aa_line_twin_id = template


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # WHAT IS BOLTED ON, PER VARIANT. On the template it could only ever be
    # one part, and the ATL horizontals take a 2x2 angle OF THEIR OWN LENGTH
    # (0662116HPA for 11'6", 0662106HPA for 10'6"...) - so once the RAW
    # lengths are variants of one product the angle has to live on each of
    # them. The template's fields stay as the fallback for everything else.
    aa_variant_prep_part_id = fields.Many2one(
        'product.product', string='Add When Preparing (this variant)',
        help='A part bolted on at Track Prep because this piece comes without '
             'it - the 2x2 angle of the same length on an ATL horizontal. '
             'Wins over the product\'s own setting.')
    aa_variant_prep_part_qty = fields.Float(
        string='Per Piece (this variant)', default=1.0, digits='Product Unit')
    aa_variant_prep_note = fields.Char(
        string='Preparation Note (this variant)',
        help='Printed on the Track Prep card whenever this piece is used.')

    def _aa_prep_part(self):
        """(part, qty per piece) bolted on when this is prepared, or (empty, 0)."""
        self.ensure_one()
        if self.aa_variant_prep_part_id:
            return self.aa_variant_prep_part_id, (self.aa_variant_prep_part_qty or 1.0)
        template = self.product_tmpl_id
        if template.aa_prep_part_id:
            return template.aa_prep_part_id, (template.aa_prep_part_qty or 1.0)
        return self.env['product.product'], 0.0

    def _aa_prep_note(self):
        self.ensure_one()
        return self.aa_variant_prep_note or self.product_tmpl_id.aa_prep_note or ''

    def _aa_line(self):
        self.ensure_one()
        value = _line_value(self)
        if value:
            return (value.name or '').strip().lower()
        return self.product_tmpl_id.aa_hw_line or False

    def _aa_line_twin(self):
        """The same part from the other line, variant for variant."""
        self.ensure_one()
        Product = self.env['product.product']
        # A LINE CHOSEN ON THE VARIANT: the twin is the sibling with every
        # other value the same and the other line. Active ones only - Odoo
        # archives the combinations that were never stocked (a Black ATL
        # piece), and an archived variant is not a part anybody can use.
        value = _line_value(self)
        if value:
            rest = _names(self) - {(value.name or '').strip().lower()}
            mine = (value.name or '').strip().lower()
            same = self.product_tmpl_id.with_context(active_test=True).product_variant_ids.filtered(
                lambda v: v != self and _line_value(v)
                and (_line_value(v).name or '').strip().lower() != mine
                and _names(v) - {(_line_value(v).name or '').strip().lower()} == rest)
            return same if len(same) == 1 else Product
        template = self.product_tmpl_id.aa_line_twin_id
        if not template:
            return Product
        variants = template.product_variant_ids
        if len(variants) <= 1:
            return variants
        mine = _names(self)
        same = variants.filtered(lambda v: _names(v) == mine)
        if len(same) == 1:
            return same
        # ONE SIDE MAY CARRY A VALUE THE OTHER HAS NOT GOT - the CHI jamb
        # bracket comes in colours and the ATL one only Galvanized, so its
        # template may hold the size alone. Nested is still one answer.
        close = variants.filtered(
            lambda v: _names(v) and (_names(v) <= mine or mine <= _names(v)))
        return close if len(close) == 1 else Product

    def _aa_for_line(self, line):
        """This part as it is on a door of `line`: its twin when it must match
        and belongs to the other line, itself otherwise."""
        self.ensure_one()
        template = self.product_tmpl_id
        if not line or not template.aa_line_must_match or \
                not self._aa_line() or self._aa_line() == line:
            return self
        return self._aa_line_twin() or self


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    aa_hw_line = fields.Selection(
        LINES, string='Hardware Line', copy=False, tracking=True,
        help='The line the jamb brackets, hinges and bottom brackets of this '
             'order come from. Blank is CHI. Change it from Orders to Make, '
             'which swaps the parts on the Work Order and the jobs.')

    def _aa_open_line_moves(self):
        """Every open move this order still picks or consumes."""
        self.ensure_one()
        Move = self.env['stock.move']
        Picking = self.env['stock.picking']
        pickings = self.picking_ids | Picking.search([('origin', '=', self.name)])
        moves = pickings.move_ids
        todo = moves
        while todo:
            more = todo.move_dest_ids - moves
            moves |= more
            todo = more
        jobs = self.env['mrp.production'].search([
            ('origin', '=', self.name), ('state', 'not in', ('done', 'cancel'))])
        moves |= jobs.move_raw_ids
        return moves.filtered(lambda m: m.state not in ('done', 'cancel')) or Move

    def _aa_current_line(self):
        self.ensure_one()
        if self.aa_hw_line:
            return self.aa_hw_line
        for move in self._aa_open_line_moves():
            template = move.product_id.product_tmpl_id
            if template.aa_line_must_match and template.aa_hw_line:
                return template.aa_hw_line
        return 'chi'

    def aa_set_hw_line(self, line):
        """Make this order with `line` ('chi' or 'atl'): swap its must-match
        parts for their twins wherever they are still to be picked."""
        if line not in LINE_NAMES:
            raise UserError(_('Unknown hardware line: %s', line))
        if not self.env.su and not self.env.user.has_group('stock.group_stock_user'):
            raise UserError(_('Only the warehouse can change an order\'s hardware line.'))
        for order in self.sudo():
            moves = order._aa_open_line_moves().filtered(
                lambda m: m.product_id.product_tmpl_id.aa_line_must_match
                and m.product_id.product_tmpl_id.aa_hw_line
                and m.product_id.product_tmpl_id.aa_hw_line != line)
            # ALL OR NOTHING: half a door in each line is the one thing this
            # exists to prevent.
            orphans = moves.filtered(lambda m: not m.product_id._aa_line_twin())
            if orphans:
                raise UserError(_(
                    '%(order)s cannot be made with %(line)s: there is no %(line)s '
                    'part for %(parts)s. Pair it under Inventory > Products > '
                    'Hardware Line first.',
                    order=order.name, line=LINE_NAMES[line],
                    parts=', '.join(sorted(set(
                        orphans.mapped('product_id.display_name'))))))
            picked = moves.filtered('picked')
            if picked:
                raise UserError(_(
                    '%(order)s: %(parts)s already picked. Put them back on the '
                    'shelf first.', order=order.name, parts=', '.join(sorted(set(
                        picked.mapped('product_id.display_name'))))))
            swapped = []
            if moves:
                moves._do_unreserve()
                for move in moves:
                    twin = move.product_id._aa_line_twin()
                    swapped.append((move.product_id.display_name, twin.display_name))
                    move.write({'product_id': twin.id})
                moves._action_assign()
            order.aa_hw_line = line
            order._aa_refresh_cards()
            body = Markup('<p>%s</p>') % _('Hardware line set to %s.', LINE_NAMES[line])
            if swapped:
                body += Markup('<ul>%s</ul>') % Markup('').join(
                    Markup('<li>%s &#8594; %s</li>') % pair for pair in sorted(set(swapped)))
            order.message_post(body=body)
            for picking in moves.mapped('picking_id'):
                picking.message_post(body=body)
        return True

    def _aa_refresh_cards(self):
        """The kit card is drawn from the kit's BoM, which does not move, so it
        is redrawn to show the parts of the line now chosen."""
        jobs = self.env['mrp.production'].search([
            ('origin', 'in', self.mapped('name')), ('state', 'not in', ('done', 'cancel'))])
        if jobs and hasattr(jobs, '_compute_aa_shop_spec'):
            jobs._compute_aa_shop_spec()

    def aa_use_twin(self, product_id):
        """Use the other line's part for ONE part that does not have to match
        the door - an ATL horizontal in place of a CHI one - and add what has
        to be bolted on to prepare it."""
        if not self.env.su and not self.env.user.has_group('stock.group_stock_user'):
            raise UserError(_('Only the warehouse can change the parts of an order.'))
        product = self.env['product.product'].browse(int(product_id)).exists()
        twin = product and product._aa_line_twin()
        if not twin:
            raise UserError(_('That part has no counterpart in the other line.'))
        if product.product_tmpl_id.aa_line_must_match:
            raise UserError(_('%s has to match the door: change the whole '
                              'order\'s hardware line instead.', product.display_name))
        for order in self.sudo():
            moves = order._aa_open_line_moves().filtered(lambda m: m.product_id == product)
            if moves.filtered('picked'):
                raise UserError(_('%s is already picked.', product.display_name))
            if not moves:
                continue
            moves._do_unreserve()
            moves.write({'product_id': twin.id})
            moves._action_assign()
            jobs = moves.mapped('raw_material_production_id')
            jobs.aa_use_prep_parts()
            order._aa_refresh_cards()
            order.message_post(body=_('%(old)s replaced by %(new)s.',
                                      old=product.display_name, new=twin.display_name))
        return True


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    aa_hw_line = fields.Selection(
        LINES, string='Hardware Line', compute='_compute_aa_hw_line',
        help='The line its jamb brackets, hinges and bottom brackets come from.')

    def _compute_aa_hw_line(self):
        # SHOWN ONLY WHERE IT MEANS SOMETHING: a transfer with no jamb
        # bracket, hinge or bottom bracket on it has no line to speak of.
        for picking in self:
            line = False
            for move in picking.move_ids:
                template = move.product_id.product_tmpl_id
                if template.aa_line_must_match and template.aa_hw_line:
                    line = template.aa_hw_line
                    break
            picking.aa_hw_line = line


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _aa_line_for_card(self):
        """The order's line, for the Shop Floor cards (False: not one of ours)."""
        self.ensure_one()
        order = self.env['sale.order'].sudo().search([('name', '=', self.origin)], limit=1) \
            if self.origin else False
        return order._aa_current_line() if order else False

    def aa_use_prep_parts(self):
        """Add what the RAW parts of this job need bolted on (the 2x2 angle of
        an ATL horizontal), once."""
        for job in self.filtered(lambda j: j.state not in ('done', 'cancel')):
            have = job.move_raw_ids.filtered(lambda m: m.state != 'cancel').mapped('product_id')
            add = []
            for move in job.move_raw_ids.filtered(lambda m: m.state != 'cancel'):
                part, per = move.product_id._aa_prep_part()
                if part and part not in have:
                    qty = move.product_uom_qty * per
                    add.append((0, 0, job._get_move_raw_values(part, qty, part.uom_id)))
                    have |= part
            if add:
                job.move_raw_ids = add
                job.move_raw_ids.filtered(lambda m: m.state == 'draft')._action_confirm()
        return True
