import json
import logging

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_sale.controllers.cart import Cart

from odoo.addons.spring_engineering.controllers.main import add_assembly_lines, quote_assembly

from .door_options import Catalog
from .models import AA_DRUMS, AA_HL_DRUMS, AA_LIFT_TYPES, AA_STD_DRUMS, AA_TRACK_TYPES

_logger = logging.getLogger(__name__)

MAX_LINES = 50
MAX_QTY = 500


class AADealerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if not counters:
            # Only on the /my page render. The counters RPC must return counters only,
            # otherwise the portal JS looks for a placeholder that does not exist.
            values['aa_is_dealer'] = request.env.user.partner_id._aa_is_on_account_dealer()
        return values


class AAOptionPricing:
    """Kit + options (tracks, cables, springs) pricing shared by the dealer Quick Order
    and the shop hardware-kit page."""

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

    def _door_data(self, variant, no_variant, line):
        options = set(no_variant.mapped('name'))
        color = variant.product_template_attribute_value_ids.filtered(
            lambda v: v.attribute_id.name == 'Finish Color')[:1].name or 'White'
        def num(key):
            try:
                return float(line.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0
        return {
            'height': num('height_in'),
            'lift': line.get('lift_type') or 'standard',
            'high_lift': num('high_lift'),
            'track_type': line.get('track_type') or '',
            'drum': line.get('drum') or '',
            'color': 'Black' if 'Black' in color else 'White',
            'tracks': 'Tracks' in options,
            'cables': 'Cables' in options,
        }

    def _spring_factor(self, partner):
        """Springs are priced like the rest of the dealer's order: cost + dealer margin.
        No margin set -> the Spring Engineering website markup."""
        margin = partner.commercial_partner_id.aa_dealer_margin
        return (1.0 + margin / 100.0) if margin else None

    def _spring_quote(self, partner, variant, no_variant, line):
        """(quote, note): the Spring Engineering quote for this door, or a note why not."""
        if 'Springs' not in set(no_variant.mapped('name')):
            return None, None
        spec = line.get('spring_spec')
        if not isinstance(spec, dict) or not spec.get('springsSpec'):
            return None, "Springs: enter the door weight and height so the springs can be calculated"
        quote = quote_assembly(spec, factor=self._spring_factor(partner))
        if quote.get('error'):
            return None, f"Springs: {quote['error']}"
        return quote, None

    def _priced_options(self, partner, variant, no_variant, line, qty, catalog):
        """Prepared tracks / cables / springs for this door, priced for the dealer.
        Unpriced ones become notes."""
        items, notes = catalog.door_items(self._door_data(variant, no_variant, line))
        extras = []
        quote, spring_note = self._spring_quote(partner, variant, no_variant, line)
        if spring_note:
            notes.append(spring_note)
        if quote:
            spec_lines = quote['description'].split('\n')[1:-1]
            extras.append({'label': 'Springs', 'product': None, 'quote': quote, 'qty': 1,
                           'unit_price': quote['total'],
                           'name': '; '.join(spec_lines) + ' (cones, spring and labor included)'})
        for product, per_door, label in items:
            price = self._unit_price(partner, product, request.env['product.template.attribute.value'], qty * per_door)
            if price <= 0:
                notes.append(f"{label}: {product.display_name} has no price yet - AA will quote it")
                continue
            extras.append({'label': label, 'product': product, 'qty': per_door, 'unit_price': price})
        return extras, notes

    def _line_note(self, line):
        parts = []
        track = dict(AA_TRACK_TYPES).get(line.get('track_type'))
        lift = dict(AA_LIFT_TYPES).get(line.get('lift_type'))
        if track or lift:
            lift_txt = lift or ''
            if line.get('lift_type') == 'highlift' and line.get('high_lift'):
                lift_txt += f' {str(line.get("high_lift"))[:8]}"'
            parts.append(f"Track: {track or '-'} | Lift: {lift_txt}")
        drum = line.get('drum')
        if drum in dict(AA_DRUMS):
            parts.append(f"Drum: {drum}")
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
        for warning in (line.get('spring_warnings') or [])[:3]:
            parts.append(f"SPRING WARNING: {str(warning)[:200]}")
        return " | ".join(parts)


class AADealerOrder(AAOptionPricing, http.Controller):

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
    def dealer_order_price(self, template_id, ptav_ids, qty=1, line=None, **kw):
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
        extras, notes = self._priced_options(partner, variant, no_variant, line or {}, qty, Catalog(request.env))
        door_unit = unit + sum(e['unit_price'] * e['qty'] for e in extras)
        return {
            'unit_price': door_unit,
            'subtotal': door_unit * qty,
            'kit_price': unit,
            'extras': [{'label': e['label'], 'name': e.get('name') or e['product'].display_name,
                        'qty': e['qty'], 'unit_price': e['unit_price']} for e in extras],
            'notes': notes,
        }

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
        catalog = Catalog(request.env)
        order_lines = []
        try:
            for idx, line in enumerate(lines, start=1):
                template = products.filtered(lambda t: t.id == int(line.get('template_id') or 0))
                if not template:
                    raise ValidationError(_("Line %s: choose a kit.", idx))
                qty = int(line.get('qty') or 0)
                if qty < 1 or qty > MAX_QTY:
                    raise ValidationError(_("Line %s: quantity must be between 1 and %s.", idx, MAX_QTY))
                self._check_series(template, line, idx)
                variant, no_variant = self._resolve_combination(template, line.get('ptav_ids'))
                if self._unit_price(partner, variant, no_variant, qty) <= 0:
                    raise ValidationError(_(
                        "Line %s: no price is set for this kit yet. Please call AA Impact.", idx))
                track_vals = self._track_values(line, idx, variant)
                extras, opt_notes = self._priced_options(partner, variant, no_variant, line, qty, catalog)
                note = " | ".join(filter(None, [self._line_note(line)] + opt_notes))
                order_lines.append((variant, no_variant, qty, note, track_vals, extras, idx, line))
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
        for variant, no_variant, qty, note, track_vals, extras, idx, line in order_lines:
            sol = request.env['sale.order.line'].sudo().create({
                **track_vals,
                'order_id': order.id,
                'product_id': variant.id,
                'product_no_variant_attribute_value_ids': [fields.Command.set(no_variant.ids)],
                'product_uom_qty': qty,
            })
            kit_drum = variant.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_id.name == 'Drum')[:1]
            if track_vals.get('aa_drum') and kit_drum and not kit_drum.name.startswith(track_vals['aa_drum']):
                note = f"{note} | HIGH LIFT DRUM NOT IN KIT - swap to {track_vals['aa_drum']}"
            if note:
                sol.name = f"{sol.name}\n{note}"
            door = f"Door {idx}" + (f" ({(line.get('tag') or '').strip()[:80]})" if (line.get('tag') or '').strip() else "")
            for extra in extras:
                if extra.get('quote'):
                    booked = add_assembly_lines(order, extra['quote'], qty=qty, note=f"Springs for {door}")
                    if booked.get('error'):
                        order.message_post(body=_("Springs for %(door)s were not added: %(err)s",
                                                  door=door, err=booked['error']))
                    continue
                request.env['sale.order.line'].sudo().create({
                    'order_id': order.id,
                    'product_id': extra['product'].id,
                    'product_uom_qty': extra['qty'] * qty,
                    'name': f"{extra['product'].display_name}\n{extra['label']} for {door}",
                })
        try:
            order.with_context(send_email=True).action_confirm()
        except UserError as e:
            _logger.warning("Dealer quick order %s left as quotation: %s", order.name, e)
        order.message_post(body=_("Placed from the dealer Quick Order page by %s (charged to account).",
                                  request.env.user.name))
        return {'redirect': order.get_portal_url()}

    def _check_series(self, template, line, idx):
        """The kit comes from the door width (AA Calculator): <=144" 1200, <=194" 1600, <=220" 1800."""
        try:
            width = float(line.get('width_in') or 0)
        except (TypeError, ValueError):
            width = 0.0
        if width <= 0:
            raise ValidationError(_("Line %s: enter the door width.", idx))
        if width > 220:
            raise ValidationError(_("Line %s: doors wider than 18' 4\" need a special order. Please call AA Impact.", idx))
        series = 'AA-1200' if width <= 144 else 'AA-1600' if width <= 194 else 'AA-1800'
        if not template.name.startswith(series):
            raise ValidationError(_("Line %(idx)s: a %(w)s\" wide door takes the %(s)s kit.",
                                    idx=idx, w=int(width) if width == int(width) else width, s=series))

    def _track_values(self, line, idx, variant):
        """Track type / lift type / high lift, validated with the AA Calculator rules."""
        track = line.get('track_type') or ''
        lift = line.get('lift_type') or ''
        if track not in dict(AA_TRACK_TYPES):
            raise ValidationError(_("Line %s: choose the track type.", idx))
        if lift not in dict(AA_LIFT_TYPES):
            raise ValidationError(_("Line %s: choose the lift type.", idx))
        high_lift = 0.0
        if lift == 'highlift':
            try:
                high_lift = float(line.get('high_lift') or 0)
            except (TypeError, ValueError):
                high_lift = 0.0
            if high_lift <= 0 or high_lift > 300:
                raise ValidationError(_("Line %s: enter the high lift in inches.", idx))
        drum = line.get('drum') or ''
        allowed = AA_HL_DRUMS if lift == 'highlift' else AA_STD_DRUMS
        if drum not in allowed:
            raise ValidationError(_("Line %s: choose a drum for this lift type.", idx))
        kit_drum = variant.product_template_attribute_value_ids.filtered(
            lambda v: v.attribute_id.name == 'Drum')
        kit_has_drum = variant.product_tmpl_id.attribute_line_ids.filtered(
            lambda l: l.attribute_id.name == 'Drum').value_ids.filtered(lambda v: v.name.startswith(drum))
        # The kit variant must carry the chosen drum. Only a high-lift drum the kit
        # does not offer yet is allowed through, flagged on the line for AA to swap.
        if kit_drum and not kit_drum[0].name.startswith(drum) and (kit_has_drum or lift != 'highlift'):
            raise ValidationError(_("Line %s: drum %s is not available for this kit.", idx, drum))
        return {'aa_track_type': track, 'aa_lift_type': lift, 'aa_high_lift': high_lift,
                'aa_drum': drum}


KIT_EXTRAS = {'Springs', 'Tracks', 'Cables'}
SESSION_KEY = 'aa_kit_door'


class AAKitCart(AAOptionPricing, Cart):
    """The shop's hardware-kit page: when Springs / Tracks / Cables are ticked the
    page asks for the door (size, weight, track, lift) and those extras are priced
    and added to the cart next to the kit, exactly like the dealer Quick Order."""

    def _pricelist(self, partner):
        # The shop's own pricelist: public price for visitors, the dealer's for a dealer.
        return request.pricelist

    def _shop_kit(self, template_id):
        return request.env['product.template'].sudo().browse(int(template_id or 0)).exists().filtered(
            'aa_dealer_quick_order')

    @route('/aa/kit/extras', type='jsonrpc', auth='public', website=True, sitemap=False)
    def aa_kit_extras(self, template_id, ptav_ids, door=None, qty=1, **kw):
        """Price the ticked extras for the door entered on the kit page, and remember
        the door for when the kit is added to the cart."""
        template = self._shop_kit(template_id)
        if not template:
            return {'error': _("Product not available.")}
        door = door if isinstance(door, dict) else {}
        try:
            variant, no_variant = self._resolve_combination(template, ptav_ids)
        except ValidationError as e:
            return {'error': str(e.args[0])}
        stored = dict(request.session.get(SESSION_KEY) or {})
        stored[str(template.id)] = door
        request.session[SESSION_KEY] = stored
        partner = request.env.user.partner_id
        qty = max(1, min(int(qty or 1), MAX_QTY))
        kit = self._unit_price(partner, variant, no_variant, qty)
        extras, notes = self._priced_options(partner, variant, no_variant, door, qty, Catalog(request.env))
        unit = kit + sum(e['unit_price'] * e['qty'] for e in extras)
        return {
            'kit_price': kit,
            'unit_price': unit,
            'extras': [{'label': e['label'], 'name': e.get('name') or e['product'].display_name,
                        'qty': e['qty'], 'unit_price': e['unit_price']} for e in extras],
            'notes': notes,
        }

    @route()
    def add_to_cart(self, product_template_id, product_id, quantity=1.0, uom_id=None,
                    product_custom_attribute_values=None, no_variant_attribute_value_ids=None,
                    linked_products=None, **kwargs):
        template = self._shop_kit(product_template_id)
        no_variant = request.env['product.template.attribute.value'].sudo().browse(
            [int(v) for v in no_variant_attribute_value_ids or []]).exists()
        wanted = KIT_EXTRAS & set(no_variant.mapped('name')) if template else set()
        plan = None
        if wanted:
            door = (request.session.get(SESSION_KEY) or {}).get(str(template.id)) or {}
            variant = request.env['product.product'].sudo().browse(int(product_id)).exists()
            missing = []
            if not float(door.get('height_in') or 0):
                missing.append(_("door height"))
            if wanted & {'Tracks', 'Cables'} and not door.get('track_type'):
                missing.append(_("track type"))
            if 'Springs' in wanted and not float(door.get('weight') or 0):
                missing.append(_("door weight"))
            if missing:
                raise UserError(_("To add %(extras)s, enter the %(missing)s on the product page.",
                                  extras=", ".join(sorted(wanted)), missing=", ".join(missing)))
            qty = max(1, int(quantity or 1))
            extras, notes = self._priced_options(request.env.user.partner_id, variant, no_variant,
                                                 door, qty, Catalog(request.env))
            plan = (variant, door, qty, extras, notes)

        result = super().add_to_cart(
            product_template_id, product_id, quantity=quantity, uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            linked_products=linked_products, **kwargs)

        if plan:
            self._aa_add_extras(*plan)
            order = request.cart
            result['cart_quantity'] = order.cart_quantity
        return result

    def _aa_add_extras(self, variant, door, qty, extras, notes):
        order = request.cart
        if not order:
            return
        kit_line = order.order_line.filtered(lambda l: l.product_id == variant).sorted('id')[-1:]
        info = " | ".join(filter(None, [self._line_note(door)] + notes))
        if kit_line and info and info not in (kit_line.name or ''):
            kit_line.name = f"{kit_line.name}\n{info}"
        for extra in extras:
            if extra.get('quote'):
                before = order.order_line
                booked = add_assembly_lines(order, extra['quote'], qty=qty, note="Springs for the kit above")
                if booked.get('error'):
                    raise UserError(booked['error'])
                (order.order_line - before).write({'linked_line_id': kit_line.id})
                continue
            order.with_context(skip_cart_verification=True)._cart_add(
                product_id=extra['product'].id,
                quantity=extra['qty'] * qty,
                linked_line_id=kit_line.id,
            )
        order._verify_cart_after_update()
