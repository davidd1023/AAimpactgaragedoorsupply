import base64
import json
import logging

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_sale.controllers.cart import Cart

from odoo.addons.spring_engineering.controllers.main import add_assembly_lines, quote_assembly

from .door_options import TRIM_ATTRIBUTES, TRIM_COLOURS, Catalog
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
            values['aa_resale_state'] = request.env.user.partner_id.aa_resale_state
        return values

    # --- tax-exempt dealer registration ---------------------------------------
    #
    # THE DEALER'S OWN PAGE. The owner, 2026-10-19: the exemption exists but
    # "every dealer has to be set up by hand". This is where they hand the
    # certificate over - signed in, so it attaches to a real account rather
    # than making a contact somebody has to merge later.

    # WHAT A CERTIFICATE MAY BE. A tax document is a PDF or a photograph of
    # one; anything else arriving here is either a mistake or an attempt, and
    # both are refused the same way.
    RESALE_TYPES = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }
    # Big enough for a scanned page, small enough that a public form is not a
    # way of filling the database.
    RESALE_MAX_BYTES = 8 * 1024 * 1024

    def _aa_resale_values(self, **extra):
        partner = request.env.user.partner_id
        values = {
            "partner": partner,
            "page_name": "resale_certificate",
            "error": "",
            "done": False,
        }
        values.update(extra)

        return values

    @route("/my/resale-certificate", type="http", auth="user", website=True,
           methods=["GET"], sitemap=False)
    def aa_resale_form(self, **kwargs):
        return request.render(
            "aa_dealer_orders.portal_resale_certificate",
            self._aa_resale_values(done=bool(kwargs.get("done"))))

    @route("/my/resale-certificate", type="http", auth="user", website=True,
           methods=["POST"], sitemap=False)
    def aa_resale_submit(self, **post):
        partner = request.env.user.partner_id
        upload = request.httprequest.files.get("certificate")

        try:
            data = self._aa_resale_file(upload)
            partner._aa_resale_submit(
                certificate=data,
                filename=upload.filename,
                number=(post.get("number") or "").strip(),
                expiry=(post.get("expiry") or "").strip(),
            )
        except (UserError, ValidationError) as error:
            return request.render(
                "aa_dealer_orders.portal_resale_certificate",
                self._aa_resale_values(error=error.args[0] if error.args else str(error)))

        # REDIRECTED RATHER THAN RENDERED, so a refresh does not upload the
        # certificate a second time.
        return request.redirect("/my/resale-certificate?done=1")

    def _aa_resale_file(self, upload):
        """The uploaded certificate as base64, or a plain refusal."""
        if not upload or not upload.filename:
            raise UserError(_("Choose the certificate file to upload."))

        extension = upload.filename.rsplit(".", 1)[-1].lower() \
            if "." in upload.filename else ""

        if extension not in self.RESALE_TYPES:
            raise UserError(_(
                "A certificate has to be a PDF or a photograph (PDF, PNG or "
                "JPG). %(name)s is neither.", name=upload.filename))

        data = upload.read(self.RESALE_MAX_BYTES + 1)

        if len(data) > self.RESALE_MAX_BYTES:
            raise UserError(_(
                "That file is bigger than 8 MB. Send a smaller scan, or email "
                "it to us."))

        if not data:
            raise UserError(_("That file is empty."))

        return base64.b64encode(data)


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
            'trims': self._trim_colour(no_variant),
            'width': num('width_in'),
            'height': num('height_in'),
            'lift': line.get('lift_type') or 'standard',
            'high_lift': num('high_lift'),
            'track_type': line.get('track_type') or '',
            'drum': line.get('drum') or '',
            'color': 'Black' if 'Black' in color else 'White',
            'tracks': 'Tracks' in options,
            'cables': 'Cables' in options,
        }

    @staticmethod
    def _trim_colour(no_variant):
        """The trim colour picked on the kit's Trims option, or '' for No Trims."""
        for ptav in no_variant.filtered(lambda v: v.attribute_id.name in TRIM_ATTRIBUTES):
            word = (ptav.name or '').split(',')[0].split(' ')[0].strip()
            if word in TRIM_COLOURS:
                return word
        return ''

    def _spring_factor(self, partner):
        """No dealer margin on springs (owner, 2026-10-16).

        A spring sells at one price for everybody: the Spring Engineering
        per-pound sale price plus cones and filler at cost. None keeps that.
        """
        return None

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
            # A trim with no cost yet still carries the $1 placeholder price, so cost is checked too.
            if price <= 0 or (label == 'Plastic Trims' and product.standard_price <= 0):
                notes.append(f"{label}: {product.display_name} has no price yet - AA will quote it")
                continue
            extra = {'label': label, 'product': product, 'qty': per_door, 'unit_price': price}
            if label == 'Plastic Trims':
                extra['name'] = f"{per_door} x {product.display_name} (18' pieces, sold whole)"
            extras.append(extra)
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
        # THE KEYS THE FORM ACTUALLY POSTS. Both callers pass a dict holding
        # width_in and height_in - _track_values reads them that way, and so
        # does the validation above - while this read 'width' and 'height',
        # which are in neither. The door size was therefore never written into
        # the note, so it never reached the order line and never reached the
        # work order sheet. The plain keys are still read second, in case
        # something older passes them.
        dims = []
        for keys, label in ((('width_in', 'width'), 'W'),
                            (('height_in', 'height'), 'H')):
            val = ''

            for key in keys:
                if line.get(key) not in (None, '', False):
                    val = line.get(key)
                    break

            try:
                number = float(val)
            except (TypeError, ValueError):
                number = None

            if number:
                # Inches, which is what the form collects.
                val = f'{number:g}"'
            elif number is not None:
                val = ''
            else:
                val = str(val or '').strip()[:20]

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
                if self._trim_colour(no_variant) and not float(line.get('height_in') or 0):
                    raise ValidationError(_("Line %s: enter the door height for the trims.", idx))
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
# WHAT THE CUSTOMER PUT IN THEIR CUSTOM KIT, between the page and the cart.
# The same trick the door box above uses, for the same reason: /shop/cart/add
# is Odoo's own route and carries no room for a parts list, so the page leaves
# it here and add_to_cart picks it up. Keyed by template, so two tabs on two
# kits do not overwrite each other.
CUSTOM_KIT_KEY = 'aa_custom_kit_parts'
# A guard rather than a policy: nobody builds a kit of two hundred different
# parts, and an unbounded list from a browser is an unbounded list.
MAX_CUSTOM_PARTS = 60
MAX_CUSTOM_QTY = 500


class AAKitCart(AAOptionPricing, Cart):
    """The shop's hardware-kit page: when Springs / Tracks / Cables are ticked or a
    trim colour is picked, the page asks for the door (size, weight, track, lift) and those extras are priced
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
        # AND ONTO THE LINE, IF THE KIT IS ALREADY IN THE CART.
        #
        # This page prices on a debounce and the door is only written to the
        # order when the kit is ADDED. Add to Cart does not wait for the
        # debounce, so the cart request could go out first and the line was
        # written with whatever the session held - nothing at all on a first
        # order, and the previous door on the next one. The page now holds the
        # click until this call returns, and this is the other half of it: if
        # the kit is already there, its note is brought up to date rather than
        # left describing a door nobody ordered.
        self._aa_sync_kit_note(variant, door, notes)
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
        if template and self._trim_colour(no_variant):
            wanted.add('Plastic Trims')
        plan = None
        if wanted:
            door = (request.session.get(SESSION_KEY) or {}).get(str(template.id)) or {}
            variant = request.env['product.product'].sudo().browse(int(product_id)).exists()
            missing = []
            if not float(door.get('height_in') or 0):
                missing.append(_("door height"))
            if 'Plastic Trims' in wanted and not float(door.get('width_in') or 0):
                missing.append(_("door width"))
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
            self._aa_popup(result, self._aa_add_extras(*plan))

        # A CUSTOM KIT'S PARTS GO IN THE SAME WAY the extras above do: as their
        # own lines, hung off the kit line, every one of them a real product.
        custom = self._custom_kit(product_template_id)

        if custom:
            order = request.cart
            kit_line = order.order_line.filtered(
                lambda line: line.product_id.product_tmpl_id == custom
                and not line.linked_line_id)[-1:]

            if kit_line:
                added = self._aa_add_custom_parts(
                    custom, kit_line, max(1, int(quantity or 1)))
                added.setdefault(kit_line.id, kit_line.product_uom_qty)
                self._aa_popup(result, added)

        return result

    # --- the custom kit ------------------------------------------------------

    def _custom_kit(self, template_id):
        """The template, if it really is a custom kit page."""
        template = request.env['product.template'].sudo().browse(
            int(template_id or 0)).exists()

        return template if template and template.aa_custom_kit else None

    def _aa_custom_kit_chosen(self, template, chosen):
        """[(variant, quantity)] - what the browser asked for, checked.

        EVERY PART IS CHECKED AGAINST WHAT IS OFFERED, not against what was
        sent. The list comes from a browser, so a variant that belongs to no
        offered product - or a spring, a track or a cable - does not reach a
        cart however it is posted.
        """
        allowed = template._aa_custom_kit_parts()
        variants = request.env['product.product'].sudo().browse([
            int(part.get('variant_id') or 0)
            for part in (chosen or [])[:MAX_CUSTOM_PARTS]
        ]).exists()
        by_id = {variant.id: variant for variant in variants
                 if variant.product_tmpl_id in allowed}
        picked = []

        for part in (chosen or [])[:MAX_CUSTOM_PARTS]:
            variant = by_id.get(int(part.get('variant_id') or 0))

            if not variant:
                continue

            try:
                quantity = float(part.get('quantity') or 0)
            except (TypeError, ValueError):
                continue

            if 0 < quantity <= MAX_CUSTOM_QTY:
                picked.append((variant, quantity))

        return picked

    @route('/aa/custom-kit/price', type='jsonrpc', auth='public', website=True)
    def aa_custom_kit_price(self, template_id, parts=None, qty=1, **kwargs):
        """Price what is in the kit so far, and remember it for the cart."""
        template = self._custom_kit(template_id)

        if not template:
            return {'error': _("That is not a custom kit.")}

        qty = max(1, int(qty or 1))
        picked = self._aa_custom_kit_chosen(template, parts)
        partner = request.env.user.partner_id
        empty = request.env['product.template.attribute.value']
        rows = []
        total = 0.0

        for variant, quantity in picked:
            unit = self._unit_price(partner, variant, empty, quantity * qty)
            line = round(unit * quantity, 2)
            total += line
            rows.append({
                'variant_id': variant.id,
                'name': variant.display_name,
                'quantity': quantity,
                'unit_price': unit,
                'price': line,
            })

        # KEPT AS THE BROWSER MEANT IT, not as it was priced: the cart books
        # from this, and a price worked out now would be a price worked out
        # before the customer changed their mind.
        stored = request.session.get(CUSTOM_KIT_KEY) or {}
        stored[str(template.id)] = [
            {'variant_id': variant.id, 'quantity': quantity}
            for variant, quantity in picked]
        request.session[CUSTOM_KIT_KEY] = stored

        return {'parts': rows, 'total': round(total, 2), 'count': len(rows)}

    def _aa_add_custom_parts(self, template, kit_line, qty):
        """Book each chosen part as its own line, under the kit line.

        Returns {line id: quantity added} so the popup can say what went in.
        """
        chosen = (request.session.get(CUSTOM_KIT_KEY) or {}).get(str(template.id))
        picked = self._aa_custom_kit_chosen(template, chosen)
        added = {}

        if not picked:
            return added

        order = request.cart

        for variant, quantity in picked:
            booked = order._cart_add(
                product_id=variant.id,
                quantity=quantity * qty,
                linked_line_id=kit_line.id,
            )

            if booked.get('line_id'):
                added[booked['line_id']] = booked.get('quantity') or quantity * qty

        order._verify_cart_after_update()

        return added

    def _aa_popup(self, result, added):
        """Make the "added to your cart" popup say what actually went in.

        THE FAULT THIS FIXES, 2026-10-20: "when i put the kit into the cart,
        the only things that pop up are the kit at 1$ and a galvanized hinge
        #1 ... none of the items i added to the kit are getting added into the
        cart."

        They were going in. Core builds notification_info out of the lines IT
        added and returns it, and both kit paths in this file add their lines
        AFTER that - so the popup named the kit and nothing else, and read as
        if the parts had been dropped. The cart page had them all along; the
        popup was the only thing lying. It is rebuilt here from the lines that
        were really booked.
        """
        order = request.cart

        if not order or not added:
            return

        information = result.get('notification_info') or {}
        result['notification_info'] = {
            **self._get_cart_notification_information(order, added),
            'warning': information.get('warning'),
        }
        result['cart_quantity'] = order.cart_quantity

    def _aa_sync_kit_note(self, variant, door, notes):
        """Keep the kit line's door note in step with the page.

        Writes the note onto the kit line already in the cart, replacing a note
        put there by an earlier state of the page rather than adding a second.
        """
        order = request.cart

        if not order:
            return

        line = order.order_line.filtered(
            lambda l: l.product_id == variant).sorted('id')[-1:]

        if not line:
            return

        info = " | ".join(filter(None, [self._line_note(door)] + (notes or [])))

        if not info:
            return

        self._aa_store_door(line, door, info)

    @staticmethod
    def _aa_door_numbers(door):
        """The door as numbers, in the units the kit page collects them."""
        def number(value):
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        return {
            "width_in": number(door.get("width_in")),
            "height_in": number(door.get("height_in")),
            "weight_lb": number(door.get("weight")),
            "hi_lift_in": number(door.get("high_lift")),
        }

    def _aa_store_door(self, line, door, info):
        """Record the door on the kit line, as numbers AND as the note.

        WRITTEN TO A FIELD, NOT TO THE DESCRIPTION. `name` is a stored
        computed field: core rebuilds it from the product whenever
        linked_line_ids changes, and attaching the extras to the kit line
        changes exactly that - so a note appended here was thrown away by the
        next line this controller created. It survived only by accident, when
        the page happened to price the door once more after the kit was
        already in the cart, which is why the door came and went between
        orders. aa_spec_note is put back onto the description by
        sale_order_line._compute_name every time, so there is no race left.
        """
        if "aa_spec_note" not in line._fields:
            # spring_engineering not installed: the old behaviour, which is
            # still better than nothing.
            head = (line.name or "").split("\n")[0]

            if line.name != f"{head}\n{info}":
                line.name = f"{head}\n{info}"

            return

        line.aa_write_door(self._aa_door_numbers(door), note=info)

    def _aa_add_extras(self, variant, door, qty, extras, notes):
        """Returns {line id: quantity added}, the kit line included, so the
        popup can name the springs and tracks that went in with the kit."""
        order = request.cart
        added = {}
        if not order:
            return added
        kit_line = order.order_line.filtered(lambda l: l.product_id == variant).sorted('id')[-1:]
        info = " | ".join(filter(None, [self._line_note(door)] + notes))
        if kit_line and info:
            self._aa_store_door(kit_line, door, info)
        if kit_line:
            added[kit_line.id] = kit_line.product_uom_qty
        for extra in extras:
            if extra.get('quote'):
                before = order.order_line
                booked = add_assembly_lines(order, extra['quote'], qty=qty, note="Springs for the kit above")
                if booked.get('error'):
                    raise UserError(booked['error'])
                fresh = order.order_line - before
                fresh.write({'linked_line_id': kit_line.id})
                added.update({line.id: line.product_uom_qty for line in fresh})
                continue
            booked = order.with_context(skip_cart_verification=True)._cart_add(
                product_id=extra['product'].id,
                quantity=extra['qty'] * qty,
                linked_line_id=kit_line.id,
            )
            if booked.get('line_id'):
                added[booked['line_id']] = booked.get('quantity') or extra['qty'] * qty
        order._verify_cart_after_update()

        return added
