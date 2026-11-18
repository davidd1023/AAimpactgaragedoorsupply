"""The next hardware P.O., one per vendor.

Owner, 2026-11-18: "quiero hacer que el sistema solo me haga el proximo PO de
hardware que debo poner, y que entienda que me viene en una fecha
determinada, y que me haga el proximo PO basado en las ordenes puestas y un
pronostico del futuro". Asked how, he chose:

* ONE P.O. PER VENDOR, from the vendor each product already names, "tenerlos
  ahi hasta que el P.O. se ponga o se confirme y ya se vaya de ahi a
  purchase". A suggestion becomes an RFQ in Purchase when he presses the
  button; once that RFQ is CONFIRMED it is stock on its way and leaves the
  screen, counted from then on as coming.
* THE FORECAST IS THE AVERAGE OF WHAT HAS BEEN USED - every part that has
  gone out to a customer or into a job over the last 90 days.
* HOW MUCH AND WHEN DEPENDS ON EACH VENDOR'S LEAD TIME. CHI takes ten weeks,
  the USA suppliers days.

THE ARITHMETIC, PER PART:

    lead   = the vendor's lead time (days until this P.O. arrives)
    cycle  = days until the NEXT P.O. to that vendor would arrive after this
             one; left blank it is the lead time again, i.e. the next P.O. is
             placed the day this one lands
    need   = the open orders already placed
           + use per day x (lead + cycle)     <- orders not placed yet
           + the part's minimum (Min / Max)   <- never planned to hit zero
    have   = on hand + every confirmed P.O. still to arrive
    order  = need - have, when above nothing

Open orders and the forecast are added, not overlapped, on purpose: what is
already ordered is known, and the forecast is for the orders that will come
in while this P.O. is on the water and until the next one lands.

Products made here (anything with a bill of materials - kits, prepared
tracks) are never bought, so they are left out: their raw parts carry the
demand, because a job's consumption is counted as use.
"""
import math
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

FORECAST_DAYS_DEFAULT = 90

# Cable is stocked in FEET but bought by the REEL - "1/8" 7X19 GAC (500 FT
# REEL)". Nobody can order 1,708 ft of a 500 ft reel, so the quantity is
# rounded up to whole reels when the name says how long one is.
REEL = re.compile(r'(\d+)\s*FT\s*REEL', re.I)
# The same for anything the vendor sells by the box - Action's trims are
# "2" Uniflex Vinyl Stop 18' Dark Brown (P5), 15 pcs/box" (owner, 2026-11-18:
# "es el precio por una caja de 15 trims"). Read off the VENDOR'S description
# first, which is where the box is stated, then the product's own name.
PACK = re.compile(r'(\d+)\s*(?:pcs|pieces|pc)\s*/\s*(?:box|case|pack)', re.I)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    aa_lead_days = fields.Integer(
        'P.O. lead time (days)',
        help="How many days a purchase order to this vendor takes to arrive. "
             "Used by Inventory > Reporting > Orders to Make > Next P.O.")
    aa_cycle_days = fields.Integer(
        'Days between P.O.s',
        help="How long each P.O. to this vendor must last after it arrives. "
             "Blank means as long as the lead time.")
    aa_coil_feet = fields.Integer(
        'Spring coil length (ft)', default=7,
        help="Spring coil ('serpiente') is stocked in inches but bought in "
             "whole coils, usually 7 or 8 ft. The Next P.O. orders coil in "
             "whole coils of this length; it is chosen on the tab.")


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    aa_suggested = fields.Boolean(
        'From Orders to Make', copy=False, readonly=True,
        help="Drafted by the Next P.O. tab of Orders to Make.")


class NextPurchaseOrder(models.AbstractModel):
    _name = 'aa.next.po'
    _description = 'Next P.O. per vendor'

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------

    @api.model
    def _forecast_days(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'aa_order_coverage.forecast_days')
        try:
            days = int(raw)
        except (TypeError, ValueError):
            days = FORECAST_DAYS_DEFAULT
        return days if days > 0 else FORECAST_DAYS_DEFAULT

    @api.model
    def _stock_locations(self):
        return self.env['stock.warehouse'].search([]).mapped('lot_stock_id')

    @api.model
    def _on_hand(self, products):
        locations = self._stock_locations()
        if not locations or not products:
            return {}
        groups = self.env['stock.quant']._read_group(
            [('product_id', 'in', products.ids),
             ('location_id', 'child_of', locations.ids)],
            ['product_id'], ['quantity:sum'])
        return {p: q for p, q in groups}

    @api.model
    def _use_per_day(self, products, days):
        """What went out to customers or into jobs, a day, over `days`."""
        since = fields.Datetime.now() - timedelta(days=days)
        Move = self.env['stock.move']
        out = Move._read_group(
            [('product_id', 'in', products.ids), ('state', '=', 'done'),
             ('date', '>=', since),
             ('location_id.usage', '=', 'internal'),
             ('location_dest_id.usage', 'in', ('customer', 'production'))],
            ['product_id'], ['product_qty:sum'])
        back = Move._read_group(
            [('product_id', 'in', products.ids), ('state', '=', 'done'),
             ('date', '>=', since),
             ('location_id.usage', 'in', ('customer', 'production')),
             ('location_dest_id.usage', '=', 'internal')],
            ['product_id'], ['product_qty:sum'])
        used = {p: q for p, q in out}
        for p, q in back:
            used[p] = used.get(p, 0.0) - q
        return {p: max(q, 0.0) / days for p, q in used.items()}

    @api.model
    def _coming(self, products):
        """{product: [qty still to arrive, earliest date]} off CONFIRMED P.O.s.

        A draft is not counted: it is a suggestion until somebody confirms it.
        """
        coming = {}
        lines = self.env['purchase.order.line'].search([
            ('product_id', 'in', products.ids),
            ('order_id.state', '=', 'purchase'),
            ('display_type', '=', False),
        ])
        for line in lines:
            product = line.product_id
            left = line.product_qty - line.qty_received
            if float_compare(left, 0.0, precision_rounding=line.product_uom_id.rounding or 0.01) <= 0:
                continue
            qty = line.product_uom_id._compute_quantity(left, product.uom_id)
            entry = coming.setdefault(product, [0.0, False])
            entry[0] += qty
            when = line.date_planned and line.date_planned.date()
            if when and (not entry[1] or when < entry[1]):
                entry[1] = when
        return coming

    @api.model
    def _minimums(self, products):
        groups = self.env['stock.warehouse.orderpoint']._read_group(
            [('product_id', 'in', products.ids)],
            ['product_id'], ['product_min_qty:sum'])
        return {p: q for p, q in groups}

    @api.model
    def _bought_products(self):
        """Storable parts we buy: purchasable and not made here."""
        products = self.env['product.product'].search([
            ('is_storable', '=', True), ('purchase_ok', '=', True)])
        made = self.env['mrp.bom'].search([
            '|', ('product_tmpl_id', 'in', products.product_tmpl_id.ids),
            ('product_id', 'in', products.ids)])
        made_tmpl = set(made.filtered(lambda b: not b.product_id).product_tmpl_id.ids)
        made_var = set(made.product_id.ids)
        return products.filtered(
            lambda p: p.product_tmpl_id.id not in made_tmpl and p.id not in made_var)

    @api.model
    def _vendor_of(self, product):
        sellers = product.seller_ids.filtered(
            lambda s: (not s.product_id or s.product_id == product)
            and (not s.company_id or s.company_id == self.env.company))
        return sellers.sorted(lambda s: (s.sequence, s.id))[:1]

    @api.model
    def _lead_days(self, vendor, seller):
        return vendor.aa_lead_days or seller.delay or 1

    # ------------------------------------------------------------------
    # The answer
    # ------------------------------------------------------------------

    @api.model
    def aa_next_po(self, open_needs, family_of):
        """Per-vendor suggestions for the board.

        `open_needs` is {product: qty the open orders still want}, from the
        Orders to Make lines, and `family_of` names the family chip a product
        belongs under.
        """
        products = self._bought_products()
        products |= self.env['product.product'].browse(
            [p.id for p in open_needs if p.purchase_ok])
        days = self._forecast_days()
        on_hand = self._on_hand(products)
        use = self._use_per_day(products, days)
        coming = self._coming(products)
        minimum = self._minimums(products)
        today = fields.Date.context_today(self)

        vendors = {}
        no_vendor = []
        for product in products:
            seller = self._vendor_of(product)
            vendor = seller.partner_id
            lead = self._lead_days(vendor, seller) if vendor else 0
            cycle = (vendor.aa_cycle_days or lead) if vendor else 0
            rate = use.get(product, 0.0)
            committed = open_needs.get(product, 0.0)
            floor = minimum.get(product, 0.0)
            have = max(on_hand.get(product, 0.0), 0.0)
            arriving, next_date = coming.get(product, [0.0, False])
            need = committed + rate * (lead + cycle) + floor
            short = need - have - arriving
            rounding = product.uom_id.rounding
            if float_compare(short, 0.0, precision_rounding=rounding) <= 0:
                continue
            # Whole units: nobody orders 3.4 hinges or 17.2 inches of cable.
            qty = math.ceil(short - 1e-6)
            reel = REEL.search(product.name or '')
            if reel and int(reel.group(1)):
                size = int(reel.group(1))
                qty = math.ceil(qty / size) * size
            pack = PACK.search(seller.product_name or '') if seller else None
            pack = pack or PACK.search(product.name or '')
            if pack and int(pack.group(1)):
                size = int(pack.group(1))
                qty = math.ceil(qty / size) * size
            if seller and seller.min_qty and qty < seller.min_qty:
                qty = seller.min_qty
            # When the stock would run out at today's pace, the open orders
            # and the minimum taken off first.
            spare = have + arriving - committed - floor
            if rate > 0:
                runs_out = today + timedelta(days=max(int(spare / rate), 0))
            else:
                runs_out = today if spare < 0 else False
            family = family_of(product)
            # SPRING COIL IS BOUGHT AS WHOLE COILS (owner, 2026-11-18: "el
            # PO de muelles me lo tienes que dar en serpientes y yo debo
            # escoger el largo, que usualmente es 7 u 8 pies"). The inches
            # still to cover go to the screen, which turns them into coils
            # of whatever length is picked there.
            coil = (product.default_code or '').upper().startswith('COIL-')
            row = {
                'coil': coil,
                'need_in': short,
                'id': product.id,
                'name': product.display_name,
                'code': product.default_code or '',
                'family_id': family.id,
                'family': family.name,
                'uom': product.uom_id.name,
                'on_hand': have,
                'open': committed,
                'per_month': rate * 30,
                'coming': arriving,
                'coming_date': fields.Date.to_string(next_date) if next_date else '',
                'minimum': floor,
                'runs_out': fields.Date.to_string(runs_out) if runs_out else '',
                'qty': qty,
                'price': seller.price if seller else 0.0,
            }
            if not vendor:
                no_vendor.append(row)
                continue
            entry = vendors.setdefault(vendor.id, {
                'id': vendor.id,
                'name': vendor.display_name,
                'lead': lead,
                'lead_set': bool(vendor.aa_lead_days),
                'cycle': vendor.aa_cycle_days or 0,
                'coil_feet': vendor.aa_coil_feet or 7,
                'arrives': fields.Date.to_string(today + timedelta(days=lead)),
                'lines': [],
                'draft': False,
            })
            entry['lines'].append(row)

        drafts = self.env['purchase.order'].search([
            ('aa_suggested', '=', True),
            ('state', 'in', ('draft', 'sent', 'to approve')),
            ('partner_id', 'in', list(vendors))])
        for po in drafts:
            entry = vendors.get(po.partner_id.id)
            if entry and not entry['draft']:
                entry['draft'] = {'id': po.id, 'name': po.name,
                                  'lines': len(po.order_line), 'state': po.state}
        for entry in vendors.values():
            entry['lines'].sort(key=lambda r: (r['family'], r['name']))
        return {
            'forecast_days': days,
            'vendors': sorted(vendors.values(), key=lambda v: v['name']),
            'no_vendor': sorted(no_vendor, key=lambda r: r['name']),
        }

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    @api.model
    def aa_set_vendor_days(self, vendor_id, lead, cycle):
        if not self.env.user.has_group('purchase.group_purchase_user') and \
                not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError("Only purchasing or an inventory manager can change a vendor's lead time.")
        vendor = self.env['res.partner'].sudo().browse(int(vendor_id)).exists()
        if not vendor:
            raise UserError("That vendor no longer exists.")
        vendor.write({'aa_lead_days': max(int(lead or 0), 0),
                      'aa_cycle_days': max(int(cycle or 0), 0)})
        return True

    @api.model
    def aa_set_coil_feet(self, vendor_id, feet):
        if not self.env.user.has_group('purchase.group_purchase_user') and \
                not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError("Only purchasing or an inventory manager can change this.")
        feet = int(feet or 0)
        if not 1 <= feet <= 20:
            raise UserError("A coil length must be between 1 and 20 feet.")
        vendor = self.env['res.partner'].sudo().browse(int(vendor_id)).exists()
        if vendor:
            vendor.aa_coil_feet = feet
        return True

    @api.model
    def aa_draft_po(self, vendor_id, lines):
        """Create, or rewrite, the vendor's draft P.O. from the board.

        `lines` is [{'product_id', 'qty'}] as shown - including any quantity
        changed on the screen. A draft this tab made earlier and nobody has
        confirmed yet is REWRITTEN rather than a second one created, so the
        vendor never ends up with two suggestions for the same need.
        """
        vendor = self.env['res.partner'].browse(int(vendor_id)).exists()
        if not vendor:
            raise UserError("That vendor no longer exists.")
        wanted = []
        Product = self.env['product.product']
        for line in lines:
            product = Product.browse(int(line['product_id']))
            vals = {'product_id': product.id}
            if line.get('coils') is not None and line.get('feet'):
                # Whole coils: the line is in INCHES, the stock unit, and its
                # description says how many coils of what length that is.
                coils = int(float(line['coils'] or 0))
                feet = int(line['feet'])
                if coils <= 0:
                    continue
                vals['product_qty'] = coils * feet * 12
                vals['name'] = "%s\n%d coil%s of %d ft (%d in)" % (
                    product.display_name, coils, '' if coils == 1 else 's',
                    feet, coils * feet * 12)
            else:
                qty = float(line.get('qty') or 0)
                if qty <= 0:
                    continue
                vals['product_qty'] = qty
            wanted.append(vals)
        if not wanted:
            raise UserError("There is nothing to order from %s." % vendor.display_name)
        PO = self.env['purchase.order']
        po = PO.search([
            ('aa_suggested', '=', True), ('partner_id', '=', vendor.id),
            ('state', 'in', ('draft', 'sent'))], limit=1)
        seller = self.env['product.supplierinfo'].search(
            [('partner_id', '=', vendor.id)], limit=1)
        lead = self._lead_days(vendor, seller)
        planned = fields.Datetime.now() + timedelta(days=lead)
        values = [(0, 0, dict(vals, date_planned=planned)) for vals in wanted]
        if po:
            po.order_line.unlink()
            po.write({'order_line': values})
            po.message_post(body="Rewritten from Orders to Make > Next P.O.")
        else:
            po = PO.create({
                'partner_id': vendor.id,
                'aa_suggested': True,
                'origin': 'Orders to Make',
                'order_line': values,
            })
        return {'id': po.id, 'name': po.name}
