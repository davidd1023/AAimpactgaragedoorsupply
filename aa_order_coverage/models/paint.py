"""Paint a Galvanized part to finish an order (owner, 2026-11-19).

"si hay algun material mill finish que podamos pintar y terminar ordenes lo
vamos a hacer y aqui quiero ver que me diga eso" - Mill Finish and Galvanized
are the same thing, and anything that comes in a colour can be painted.

THE TWIN. A coloured part's Galvanized twin is the same part with the colour
swapped for Galvanized: the variant of the same product whose colour value is
Galvanized and every other value the same (hinges, rollers, brackets...), or,
for parts whose colour is in the name (RAW tracks), the product of the same
name with Galvanized in place of the colour.

THE PAINT P.O. Painting is a purchase order to a painter (a vendor ticked as
a painter in Orders to Make > Settings) for the COLOURED part. Its expected
date is the pickup date, so the order's ready date follows it. When the paint
P.O. is received, the same number of Galvanized twins comes off the shelf -
they are what went to the painter.
"""
import re

from markupsafe import Markup

from odoo import _, api, fields, models

COLOUR_ATTRIBUTES = ('colour', 'color', 'finish color', 'finish colour')
GALVANIZED = ('galvanized', 'galvanised', 'mill finish', 'mill')
NAME_COLOUR = re.compile(
    r'\b(Black|White|Bronze|Brown|Almond|Sandstone|Desert Tan|Terratone|Chocolate)\b')


def galvanized_twin(product, cache=None):
    """The Galvanized twin of a coloured part, or an empty recordset."""
    Product = product.env['product.product'].sudo()
    if not product:
        return Product
    if cache is not None and product.id in cache:
        return cache[product.id]
    twin = Product
    values = product.product_template_attribute_value_ids
    colour = values.filtered(
        lambda v: (v.attribute_id.name or '').strip().lower() in COLOUR_ATTRIBUTES)[:1]
    if colour:
        if (colour.name or '').strip().lower() not in GALVANIZED:
            rest = set((values - colour).ids)
            for variant in product.product_tmpl_id.with_context(active_test=True).product_variant_ids:
                vv = variant.product_template_attribute_value_ids
                vc = vv.filtered(lambda v: v.attribute_id == colour.attribute_id)[:1]
                if vc and (vc.name or '').strip().lower() in GALVANIZED \
                        and set((vv - vc).ids) == rest:
                    twin = variant
                    break
    else:
        name = product.name or ''
        if NAME_COLOUR.search(name) and not re.search(r'galvani[sz]ed', name, re.I):
            wanted = NAME_COLOUR.sub('Galvanized', name, count=1)
            twin = Product.search([('name', '=', wanted), ('is_storable', '=', True)], limit=1)
    if twin and not twin.is_storable:
        twin = Product
    if cache is not None:
        cache[product.id] = twin
    return twin


class ResPartner(models.Model):
    _inherit = 'res.partner'

    aa_paints_parts = fields.Boolean(
        'Paints parts',
        help="A painter: a purchase order to this vendor for a coloured part "
             "means a Galvanized one is being painted. Orders to Make uses "
             "it for the ready date, and receiving it takes the Galvanized "
             "parts off the shelf.")


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    aa_is_paint = fields.Boolean(
        'Paint P.O.', compute='_compute_aa_is_paint',
        help='Sent to a painter: Galvanized parts painted in a colour.')

    @api.depends('partner_id.aa_paints_parts')
    def _compute_aa_is_paint(self):
        for order in self:
            order.aa_is_paint = bool(order.partner_id.commercial_partner_id.aa_paints_parts
                                     or order.partner_id.aa_paints_parts)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves._aa_take_painted_galvanized()
        return moves

    def _aa_take_painted_galvanized(self):
        """A paint P.O. came back: the Galvanized twins it was made from are
        gone from the shelf. Never raises - receiving must not fail over it."""
        cache = {}
        for move in self.filtered(lambda m: m.state == 'done' and m.purchase_line_id
                                  and m.location_dest_id.usage == 'internal'
                                  and m.location_id.usage == 'supplier'):
            order = move.purchase_line_id.order_id
            if not order.aa_is_paint:
                continue
            twin = galvanized_twin(move.product_id, cache)
            if not twin:
                continue
            uom = move.product_uom if 'product_uom' in move._fields else move.product_uom_id
            qty = uom._compute_quantity(move.quantity, move.product_id.uom_id)
            if qty <= 0:
                continue
            try:
                with self.env.cr.savepoint():
                    Move = self.env['stock.move'].sudo()
                    uom_key = 'product_uom' if 'product_uom' in Move._fields else 'product_uom_id'
                    used = Move.create({
                        'product_id': twin.id,
                        'product_uom_qty': qty,
                        uom_key: twin.uom_id.id,
                        # FROM THE SHELF, not from Input: with two- or
                        # three-step receipts the paint P.O. lands in Input
                        # while the Galvanized parts were on the shelf.
                        'location_id': (move.picking_type_id.warehouse_id.lot_stock_id
                                        or move.location_dest_id).id,
                        'location_dest_id': twin.with_company(move.company_id)
                        .property_stock_inventory.id,
                        'company_id': move.company_id.id,
                        'origin': order.name,
                    })
                    used._action_confirm()
                    used.quantity = qty
                    used.picked = True
                    used._action_done()
                order.message_post(body=Markup('<p>%s</p>') % _(
                    'Received painted: %(qty)s %(twin)s taken off the shelf.',
                    qty=qty, twin=twin.display_name), subtype_xmlid='mail.mt_note')
            except Exception as error:  # noqa: BLE001
                order.message_post(body=Markup('<p>%s</p>') % _(
                    'Could not take the Galvanized %(twin)s off the shelf: %(error)s',
                    twin=twin.display_name, error=error), subtype_xmlid='mail.mt_note')
