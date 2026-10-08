import json
import logging

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)

MAX_LINES = 50
MAX_QTY = 500


class AADealerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        values['aa_is_dealer'] = request.env.user.partner_id._aa_is_on_account_dealer()
        return values


class AADealerOrder(http.Controller):

    # ── helpers ──────────────────────────────────────────────────────────────

    def _dealer_partner(self):
        partner = request.env.user.partner_id
        if request.env.user._is_public() or not partner._aa_is_on_account_dealer():
            return None
        return partner

    def _quick_order_products(self):
        return request.env['product.template'].sudo().search([
            ('aa_dealer_quick_order', '=', True),
            ('sale_ok', '=', True),
        ], order='name')

    def _pricelist(self, partner):
        return partner.property_product_pricelist or request.pricelist

    def _resolve_combination(self, template, ptav_ids):
        """Validate the selected values against the template and return (variant, no_variant_ptavs).

        Every attribute line that has values must get exactly one value, except
        multi-checkbox (no_variant) lines, which take any number (including none).
        """
        ptavs = request.env['product.template.attribute.value'].sudo().browse(
            [int(i) for i in ptav_ids or []]
        ).exists()
        if any(ptav.product_tmpl_id != template or not ptav.ptav_active for ptav in ptavs):
            raise ValidationError(_("Invalid option selected for %s.", template.name))
        for line in template.valid_product_template_attribute_line_ids:
            chosen = ptavs.filtered(lambda v: v.attribute_line_id == line)
            if line.attribute_id.display_type == 'multi':
                continue
            if len(chosen) != 1:
                raise ValidationError(_("Please choose %(attr)s for %(product)s.",
                                        attr=line.attribute_id.name, product=template.name))
        if not template._is_combination_possible(ptavs):
            raise ValidationError(_("This combination is not available for %s.", template.name))
        variant = template._get_variant_for_combination(ptavs) or template._create_product_variant(ptavs)
        if not variant:
            raise ValidationError(_("This combination is not available for %s.", template.name))
        no_variant = ptavs.filtered(lambda v: v.attribute_id.create_variant == 'no_variant')
        return variant, no_variant

    def _unit_price(self, partner, variant, no_variant, qty):
        # Same pricing as the sales order line: partner pricelist + no-variant option extras.
        pricelist = self._pricelist(partner)
        price_ctx = variant._get_product_price_context(no_variant)
        if pricelist:
            return pricelist._get_product_price(variant.with_context(**price_ctx), qty or 1.0)
        return variant.lst_price + price_ctx.get('no_variant_attributes_price_extra', 0.0)

    def _product_payload(self, template):
        lines = []
        for line in template.valid_product_template_attribute_line_ids:
            values = line.product_template_value_ids.filtered('ptav_active')
            if not values:
                continue
            lines.append({
                'id': line.id,
                'name': line.attribute_id.name,
                'multi': line.attribute_id.display_type == 'multi',
                'values': [{
                    'id': v.id,
                    'name': v.name,
                    'price_extra': v.price_extra,
                } for v in values],
            })
        return {'id': template.id, 'name': template.name, 'attributes': lines}

    # ── pages ────────────────────────────────────────────────────────────────

    @http.route('/dealer/order', type='http', auth='user', website=True, sitemap=False)
    def dealer_order_page(self, **kw):
        partner = self._dealer_partner()
        if not partner:
            return request.render('aa_dealer_orders.dealer_order_denied', {})
        products = self._quick_order_products()
        recent = request.env['sale.order'].search([
            ('partner_id', 'child_of', partner.commercial_partner_id.id),
            ('state', '=', 'sale'),
        ], order='date_order desc', limit=10)
        return request.render('aa_dealer_orders.dealer_order_page', {
            'partner': partner,
            'dealer': partner.commercial_partner_id,
            'products_json': json.dumps([self._product_payload(p) for p in products]),
            'recent_orders': recent,
            'currency': request.website.currency_id,
        })

    @http.route('/dealer/order/price', type='jsonrpc', auth='user', website=True)
    def dealer_order_price(self, template_id, ptav_ids, qty=1, **kw):
        partner = self._dealer_partner()
        if not partner:
            return {'error': _("Not available.")}
        template = self._quick_order_products().filtered(lambda t: t.id == int(template_id))
        if not template:
            return {'error': _("Product not available.")}
        try:
            variant, no_variant = self._resolve_combination(template, ptav_ids)
        except ValidationError as e:
            return {'error': str(e.args[0])}
        qty = max(1, min(int(qty or 1), MAX_QTY))
        unit = self._unit_price(partner, variant, no_variant, qty)
        return {'unit_price': unit, 'subtotal': unit * qty}

    @http.route('/dealer/order/submit', type='jsonrpc', auth='user', website=True)
    def dealer_order_submit(self, lines, po_number='', notes='', pickup_date=None, **kw):
        partner = self._dealer_partner()
        if not partner:
            return {'error': _("Only preferred dealers can use the Quick Order page.")}
        po_number = (po_number or '').strip()[:100]
        if not po_number:
            return {'error': _("Please enter your PO number.")}
        if not lines or len(lines) > MAX_LINES:
            return {'error': _("Add at least one kit to the order.")}

        products = self._quick_order_products()
        order_lines = []
        try:
            for idx, line in enumerate(lines, start=1):
                template = products.filtered(lambda t: t.id == int(line.get('template_id') or 0))
                if not template:
                    raise ValidationError(_("Line %s: choose a kit.", idx))
                qty = int(line.get('qty') or 0)
                if qty < 1 or qty > MAX_QTY:
                    raise ValidationError(_("Line %s: quantity must be between 1 and %s.", idx, MAX_QTY))
                variant, no_variant = self._resolve_combination(template, line.get('ptav_ids'))
                if self._unit_price(partner, variant, no_variant, qty) <= 0:
                    raise ValidationError(_(
                        "Line %s: no price is set for this kit yet. Please call AA Impact.", idx))
                order_lines.append((variant, no_variant, qty, self._line_note(line)))
        except (ValidationError, ValueError, TypeError) as e:
            return {'error': str(e.args[0]) if e.args else _("Invalid order.")}

        commitment_date = False
        if pickup_date:
            try:
                commitment_date = fields.Datetime.to_datetime(f"{pickup_date} 12:00:00")
            except ValueError:
                commitment_date = False

        SaleOrder = request.env['sale.order'].sudo()
        order = SaleOrder.create({
            'partner_id': partner.id,
            'website_id': request.website.id,
            'client_order_ref': po_number,
            'commitment_date': commitment_date,
            'aa_dealer_quick_order': True,
            'note': notes and notes.strip()[:2000] or False,
        })
        for variant, no_variant, qty, note in order_lines:
            sol = request.env['sale.order.line'].sudo().create({
                'order_id': order.id,
                'product_id': variant.id,
                'product_no_variant_attribute_value_ids': [fields.Command.set(no_variant.ids)],
                'product_uom_qty': qty,
            })
            if note:
                sol.name = f"{sol.name}\n{note}"
        try:
            order.with_context(send_email=True).action_confirm()
        except UserError as e:
            _logger.warning("Dealer quick order %s left as quotation: %s", order.name, e)
        order.message_post(body=_("Placed from the dealer Quick Order page by %s (charged to account).",
                                  request.env.user.name))
        return {'redirect': order.get_portal_url()}

    def _line_note(self, line):
        parts = []
        tag = (line.get('tag') or '').strip()[:80]
        if tag:
            parts.append(f"Door: {tag}")
        dims = []
        for key, label in (('width', 'W'), ('height', 'H')):
            val = (line.get(key) or '').strip()[:20]
            if val:
                dims.append(f"{label} {val}")
        if dims:
            parts.append(" x ".join(dims))
        weight = str(line.get('weight') or '').strip()[:10]
        if weight:
            parts.append(f"{weight} lb")
        return " | ".join(parts)
