"""Kit data AA asked for (idempotent, safe to run again):

* "Trims" option on every hardware kit (it was only on AA-1200).
* High-lift drums (D525-54, D575-120, D800-120) on every kit. Each new high-lift
  variant gets the BoM of its D525-216 sibling with the drum swapped for the
  high-lift drum of the same color, and its cost recomputed from that BoM.
"""
import logging

_logger = logging.getLogger(__name__)

KIT_NAMES = ['AA-1200 Hardware Kit', 'AA-1600 Hardware Kit', 'AA-1800 Hardware Kit']
HL_DRUM_VALUES = [
    ('D525-54', 'D525-54 (high lift up to 54", up to 1,000 lb)'),
    ('D575-120', 'D575-120 (high lift up to 120", up to 1,000 lb)'),
    ('D800-120', 'D800-120 (high lift, over 1,000 lb)'),
]
BASE_DRUM = 'D525-216'


def setup_kit_options(env):
    kits = env['product.template'].with_context(active_test=False).search([('name', 'in', KIT_NAMES)])
    for kit in kits:
        _add_trims(kit)
        _add_high_lift_drums(kit)


def _add_trims(kit):
    line = kit.attribute_line_ids.filtered(lambda l: l.attribute_id.name == 'Add to Your Order')[:1]
    if not line:
        return
    trims = line.attribute_id.value_ids.filtered(lambda v: v.name == 'Trims')[:1]
    if trims and trims not in line.value_ids:
        line.value_ids = [(4, trims.id)]
        _logger.info("aa_dealer_orders: added Trims to %s", kit.name)


def _add_high_lift_drums(kit):
    env = kit.env
    drum_line = kit.attribute_line_ids.filtered(lambda l: l.attribute_id.name == 'Drum')[:1]
    if not drum_line:
        return
    attr = drum_line.attribute_id
    to_add = []
    for code, label in HL_DRUM_VALUES:
        value = attr.value_ids.filtered(lambda v, c=code: v.name.startswith(c))[:1]
        if not value:
            value = env['product.attribute.value'].create({'attribute_id': attr.id, 'name': label})
        if value not in drum_line.value_ids:
            to_add.append(value.id)
    if to_add:
        drum_line.value_ids = [(4, vid) for vid in to_add]
        _logger.info("aa_dealer_orders: added %s high-lift drums to %s", len(to_add), kit.name)

    if 'mrp.bom' not in env:
        return
    Bom = env['mrp.bom']
    base_ptav = drum_line.product_template_value_ids.filtered(lambda v: v.name.startswith(BASE_DRUM))[:1]
    if not base_ptav:
        return
    for variant in kit.product_variant_ids:
        vdrum = variant.product_template_attribute_value_ids.filtered(lambda v: v.attribute_id == attr)
        code = next((c for c, _l in HL_DRUM_VALUES if vdrum and vdrum.name.startswith(c)), None)
        if not code or Bom.search_count([('product_id', '=', variant.id)]):
            continue
        sibling = kit._get_variant_for_combination(
            (variant.product_template_attribute_value_ids - vdrum) | base_ptav)
        sib_bom = sibling and Bom.search([('product_id', '=', sibling.id)], limit=1)
        if not sib_bom:
            continue
        new_bom = sib_bom.copy({'product_id': variant.id})
        hl_products = env['product.product'].search([('name', 'ilike', code)])
        for bline in new_bom.bom_line_ids.filtered(lambda l: BASE_DRUM in (l.product_id.name or '')):
            color = 'Black' if 'Black' in bline.product_id.display_name else 'White'
            pick = hl_products.filtered(lambda p: color in p.display_name)[:1] or hl_products[:1]
            if pick:
                bline.product_id = pick
        if hasattr(variant, 'button_bom_cost'):
            variant.button_bom_cost()
