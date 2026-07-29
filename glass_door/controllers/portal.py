import json
import ast
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class GlassDoorPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'door_count' in counters:
            partner = request.env.user.partner_id
            values['door_count'] = request.env['glass.door.order'].search_count(
                [('dealer_id', '=', partner.id)]
            )
        return values

    # ── Order List ────────────────────────────────────────────────────────────

    @http.route(['/my/doors', '/my/doors/page/<int:page>'], type='http',
                auth='user', website=True)
    def portal_doors(self, page=1, **kw):
        partner = request.env.user.partner_id
        domain = [('dealer_id', '=', partner.id)]

        total = request.env['glass.door.order'].search_count(domain)
        pager = portal_pager(
            url='/my/doors',
            total=total,
            page=page,
            step=20,
        )
        orders = request.env['glass.door.order'].search(
            domain, order='id desc',
            limit=20, offset=pager['offset']
        )
        return request.render('glass_door.portal_door_list', {
            'orders': orders,
            'pager': pager,
            'page_name': 'doors',
        })

    # ── New Order Form ────────────────────────────────────────────────────────

    @http.route('/my/doors/new', type='http', auth='user', website=True)
    def portal_door_new(self, **kw):
        partner = request.env.user.partner_id
        glass_types = request.env['glass.door.glass.type'].search([])
        interlayers = request.env['glass.door.interlayer'].search([])
        finishes = request.env['glass.door.frame.finish'].search([])
        motors = request.env['glass.door.motor'].search([('active', '=', True)])
        clients = request.env['glass.door.dealer.client'].search([
            ('dealer_id', '=', partner.id)
        ])
        return request.render('glass_door.portal_door_form', {
            'glass_types': glass_types,
            'interlayers': interlayers,
            'finishes': finishes,
            'motors': motors,
            'clients': clients,
            'page_name': 'doors',
            'order': None,
        })

    # ── Manage Clients ────────────────────────────────────────────────────────

    @http.route('/my/clients', type='http', auth='user', website=True)
    def portal_clients(self, **kw):
        partner = request.env.user.partner_id
        clients = request.env['glass.door.dealer.client'].search([
            ('dealer_id', '=', partner.id)
        ])
        return request.render('glass_door.portal_client_list', {
            'clients': clients,
            'page_name': 'clients',
        })

    @http.route('/my/clients/save', type='http', auth='user', website=True, methods=['POST'])
    def portal_client_save(self, **post):
        partner = request.env.user.partner_id
        client_id = int(post.get('client_id', 0))

        vals = {
            'name': post.get('name', ''),
            'dealer_id': partner.id,
            'markup': float(post.get('markup', 0)),
            'phone': post.get('phone', ''),
            'email': post.get('email', ''),
        }

        if client_id:
            client = request.env['glass.door.dealer.client'].search([
                ('id', '=', client_id), ('dealer_id', '=', partner.id)
            ], limit=1)
            if client:
                client.sudo().write(vals)
        else:
            request.env['glass.door.dealer.client'].sudo().create(vals)

        return request.redirect('/my/clients')

    @http.route('/my/clients/create_ajax', type='jsonrpc', auth='user')
    def portal_client_create_ajax(self, name, **kw):
        """Quick-create a client inline from the quote form."""
        partner = request.env.user.partner_id
        client = request.env['glass.door.dealer.client'].sudo().create({
            'name': name,
            'dealer_id': partner.id,
            'markup': 0.0,
        })
        return {'id': client.id, 'name': client.name, 'markup': client.markup}

    # ── Order Detail ──────────────────────────────────────────────────────────

    @http.route('/my/doors/<int:order_id>', type='http', auth='user', website=True)
    def portal_door_detail(self, order_id, **kw):
        partner = request.env.user.partner_id
        order = request.env['glass.door.order'].search([
            ('id', '=', order_id),
            ('dealer_id', '=', partner.id),
        ], limit=1)
        if not order:
            return request.redirect('/my/doors')
        return request.render('glass_door.portal_door_detail', {
            'order': order,
            'page_name': 'doors',
        })

    # ── Submit Order ──────────────────────────────────────────────────────────

    @http.route('/my/doors/submit', type='http', auth='user', website=True, methods=['POST'])
    def portal_door_submit(self, **post):
        partner = request.env.user.partner_id

        vals = {
            'dealer_id': partner.id,
            'job_name': post.get('job_name', ''),
            'po_number': post.get('po_number', ''),
            'dealer_client_id': int(post.get('dealer_client_id', 0)) or False,
            'job_markup': float(post.get('job_markup', 0)),
            'series': post.get('series', '1200'),
            'design_pressure': post.get('design_pressure', 'dp20'),
            'lites': int(post.get('lites', 1)),
            'frame_finish_id': int(post.get('frame_finish_id', 0)) or False,
            'frame_width': float(post.get('frame_width', 0)),
            'frame_height': float(post.get('frame_height', 0)),
            'glass_type_id': int(post.get('glass_type_id', 0)) or False,
            'interlayer_id': int(post.get('interlayer_id', 0)) or False,
            'quantity': int(post.get('quantity', 1)),
            'trim_type': post.get('trim_type', 'pvc'),
            'hardware_color': post.get('hardware_color', 'mill'),
            'track_type': post.get('track_type', 'standard'),
            'motor_id': int(post.get('motor_id', 0)) or False,
            'include_reinforcement': post.get('include_reinforcement') == 'on',
        }

        order = request.env['glass.door.order'].sudo().create(vals)

        # Misc items — submitted as a JSON array in the hidden field
        misc_json = post.get('misc_items_json', '[]')
        try:
            misc_items = json.loads(misc_json)
        except (ValueError, TypeError):
            misc_items = []
        for item in misc_items:
            desc = str(item.get('description', '')).strip()
            if not desc:
                continue
            request.env['glass.door.order.misc.line'].sudo().create({
                'order_id': order.id,
                'description': desc,
                'qty': int(item.get('qty', 1)) or 1,
                'unit_price': float(item.get('unit_price', 0)),
            })

        order.sudo().action_submit()
        return request.redirect(f'/my/doors/{order.id}')

    # ── Compute Price (AJAX) ───────────────────────────────────────────────────

    @http.route('/my/doors/compute_price', type='jsonrpc', auth='user')
    def compute_price(self, **kw):
        partner = request.env.user.partner_id
        try:
            lites = int(kw.get('lites', 1))
            frame_width = float(kw.get('frame_width', 0))
            frame_height = float(kw.get('frame_height', 0))
            glass_type_id = int(kw.get('glass_type_id', 0))
            interlayer_id = int(kw.get('interlayer_id', 0))
            quantity = int(kw.get('quantity', 1))
            trim_type = kw.get('trim_type', 'pvc')
            include_reinforcement = kw.get('include_reinforcement', False)
            motor_id = int(kw.get('motor_id', 0))
            misc_total = float(kw.get('misc_total', 0))
            job_markup = float(kw.get('job_markup', 0))

            # Adjust lites if needed
            if frame_width > 144 and lites < 2:
                lites = 2

            # Build a temporary (unsaved) record to compute values
            order = request.env['glass.door.order'].new({
                'dealer_id': partner.id,
                'frame_width': frame_width,
                'frame_height': frame_height,
                'lites': lites,
                'glass_type_id': glass_type_id,
                'interlayer_id': interlayer_id,
                'quantity': quantity,
                'trim_type': trim_type,
                'include_reinforcement': include_reinforcement,
                'motor_id': motor_id or False,
                'job_markup': job_markup,
                'series': kw.get('series', '1200'),
                'design_pressure': kw.get('design_pressure', 'dp20'),
                'frame_finish_id': int(kw.get('frame_finish_id', 0)) or False,
                'track_type': kw.get('track_type', 'standard'),
                'job_name': 'preview',
            })

            # unit_price from the computed field covers door + motor markup
            # misc_total is added directly (dealer entered sell price)
            unit = round(order.unit_price + misc_total, 2)
            total = round(unit * quantity, 2)

            return {
                'num_panels': order.num_panels,
                'panel_height': round(order.panel_height, 4),
                'glass_width': order.glass_width,
                'glass_height': order.glass_height,
                'door_weight': round(order.door_weight, 2),
                'unit_price': unit,
                'total_price': total,
                'lites': lites,
            }
        except Exception as e:
            return {'error': str(e)}
