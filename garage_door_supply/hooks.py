"""
Post-install hook: creates hardware kit products and BOMs.
Uses product default_code lookups — no XML ID dependencies.
Idempotent: skips existing kits/BOMs.
"""


def post_init_hook(env):
    _create_hardware_kits(env)


def _get_variant(env, tmpl_code, finish='UP'):
    tmpl = env['product.template'].search([('default_code', '=', tmpl_code)], limit=1)
    if not tmpl:
        return None
    variants = tmpl.product_variant_ids
    if len(variants) == 1:
        return variants[0]
    for v in variants:
        if finish in (v.default_code or ''):
            return v
        attrs = v.product_template_attribute_value_ids.mapped('name')
        if 'Unpainted' in attrs:
            return v
    return variants[0]


def _create_hardware_kits(env):
    uom_units = env['uom.uom'].search([('name', '=', 'Units')], limit=1)
    kit_categ = env['product.category'].search([('name', 'ilike', 'Hardware Kit')], limit=1)
    pub_categ = env['product.public.category'].search([('name', '=', 'Hardware Kits')], limit=1)
    site = env['website'].search([('name', 'ilike', 'AA Impact')], limit=1)

    # Component lookup
    def get(code):
        return _get_variant(env, code)

    flag        = get('CH-JA01-59')
    usa_bracket = get('CH1119D')
    drum_400    = get('CH-CD03')
    drum_525    = get('CH-CD04')
    roller_7    = get('CH-NR05-3-7')
    roller_9    = get('CH-NR05-3-9')
    center_h    = get('CH1411-0')
    lag_bolt    = get('ATL-9150000185')
    pushnut     = get('ATL-9150000207')
    cable_532   = get('ATL-9150000608')
    sleeve_532  = get('ATL-9150000622')
    stop_532    = get('ATL-9150000628')
    thimble_532 = get('ATL-9150000634')
    cable_316   = get('ATL-9150000612')
    sleeve_316  = get('ATL-9150000623')
    stop_316    = get('ATL-9150000629')
    thimble_316 = get('ATL-9150000635')

    # Check all required components exist
    required = [flag, usa_bracket, drum_400, drum_525, roller_7, roller_9,
                center_h, lag_bolt, pushnut, cable_532, sleeve_532, stop_532,
                thimble_532, cable_316, sleeve_316, stop_316, thimble_316]
    if not all(required):
        missing = [c for c in required if not c]
        return  # Skip if components not loaded yet

    reg_hinges  = {}
    half_hinges = {}
    for n in range(3, 9):
        reg_hinges[n]  = get('CH1411-' + str(n))
        half_hinges[n] = get('CH1407-' + str(n))

    DRUM    = {'1200': drum_400, '1600': drum_400, '1800': drum_525}
    CABLE   = {'1200': cable_532, '1600': cable_532, '1800': cable_316}
    SLEEVE  = {'1200': sleeve_532, '1600': sleeve_532, '1800': sleeve_316}
    STOP    = {'1200': stop_532,   '1600': stop_532,   '1800': stop_316}
    THIMBLE = {'1200': thimble_532,'1600': thimble_532,'1800': thimble_316}
    CENTER_PER_INTERM = {'1200': 3, '1600': 5, '1800': 5}
    SPRING_QTY        = {'1200': 2, '1600': 2, '1800': 4}

    for series in ['1200', '1600', '1800']:
        for panels in [4, 5, 6, 7]:
            intermediates  = panels - 1
            last_hinge_num = panels + 1      # 4p->5, 5p->6, 6p->7, 7p->8
            hinge_nums     = list(range(3, last_hinge_num + 1))
            roller9_qty    = 2 * intermediates
            pushnut_qty    = 4 + roller9_qty
            center_qty     = CENTER_PER_INTERM[series] * intermediates
            spring_qty     = SPRING_QTY[series]

            sku  = 'HK-' + series + '-' + str(panels) + 'P'
            name = series + ' Series Hardware Kit - ' + str(panels) + ' Panel'

            # Skip if kit already exists with a BOM
            kit_tmpl = env['product.template'].search(
                [('default_code', '=', sku)], limit=1)
            if kit_tmpl:
                bom = env['mrp.bom'].search(
                    [('product_tmpl_id', '=', kit_tmpl.id)], limit=1)
                if bom:
                    continue  # Already set up — skip

            # Create kit product if missing
            if not kit_tmpl:
                vals = {
                    'name': name,
                    'default_code': sku,
                    'type': 'consu',
                    'uom_id': uom_units.id,
                    'purchase_ok': False,
                    'sale_ok': True,
                    'is_published': True,
                }
                if kit_categ:
                    vals['categ_id'] = kit_categ.id
                if site:
                    vals['website_id'] = site.id
                kit_tmpl = env['product.template'].create(vals)
                if pub_categ:
                    kit_tmpl.write({'public_categ_ids': [(4, pub_categ.id)]})

            # Build BOM lines
            lines = []

            def add(product, qty):
                if product:
                    lines.append((0, 0, {
                        'product_id': product.id,
                        'product_qty': qty,
                        'product_uom_id': uom_units.id,
                    }))

            for n in hinge_nums:
                if reg_hinges.get(n):
                    add(reg_hinges[n], 2)
                if half_hinges.get(n):
                    add(half_hinges[n], 2)

            add(center_h,              center_qty)
            add(flag,                  2)
            add(usa_bracket,           spring_qty)
            add(DRUM[series],          2)
            add(roller_7,              4)
            add(roller_9,              roller9_qty)
            add(CABLE[series],         1)
            add(SLEEVE[series],        1)
            add(STOP[series],          1)
            add(THIMBLE[series],       1)
            add(lag_bolt,              50)
            add(pushnut,               pushnut_qty)

            bom = env['mrp.bom'].create({
                'product_tmpl_id': kit_tmpl.id,
                'product_qty': 1,
                'type': 'normal',
                'bom_line_ids': lines,
            })

            # Price at 30% markup over component costs
            total_cost = sum(
                (l.product_id.standard_price or l.product_id.list_price) * l.product_qty
                for l in bom.bom_line_ids
            )
            sell_price = round(total_cost * 1.30, 2)
            kit_tmpl.write({
                'standard_price': round(total_cost, 2),
                'list_price': sell_price,
            })
