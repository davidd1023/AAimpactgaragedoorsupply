from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestHardwareLine(TransactionCase):
    """ONE DOOR, ONE HARDWARE LINE (owner, 2026-11-25): jamb brackets,
    hinges and bottom brackets of a door are all CHI or all ATL."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.pick_type = cls.warehouse.pick_type_id
        Template = cls.env['product.template']

        def part(name, line, must=True, **kw):
            return Template.create(dict({
                'name': name, 'is_storable': True,
                'aa_hw_line': line, 'aa_line_must_match': must}, **kw))

        cls.chi_hinge = part('HWL Hinge CHI', 'chi')
        cls.atl_hinge = part('HWL Hinge ATL', 'atl', aa_line_twin_id=cls.chi_hinge.id)
        cls.chi_jamb = part('HWL Jamb CHI', 'chi')
        cls.atl_jamb = part('HWL Jamb ATL', 'atl', aa_line_twin_id=cls.chi_jamb.id)
        cls.chi_bottom = part('HWL Bottom CHI', 'chi')
        cls.angle = cls.env['product.product'].create(
            {'name': 'HWL 2x2 Angle', 'is_storable': True})
        cls.chi_horizontal = part('HWL Horizontal RAW CHI', 'chi', must=False)
        cls.atl_horizontal = part(
            'HWL Horizontal RAW ATL', 'atl', must=False,
            aa_line_twin_id=cls.chi_horizontal.id,
            aa_prep_part_id=cls.angle.id, aa_prep_part_qty=1.0,
            aa_prep_note='ATL horizontal: bolt the 2x2 angle on')
        cls.roller = cls.env['product.product'].create(
            {'name': 'HWL Roller', 'is_storable': True})
        cls.partner = cls.env['res.partner'].create({'name': 'HWL Dealer'})
        cls.Line = cls.env['aa.order.coverage.line']

    def _stock(self, template, qty):
        self.env['stock.quant']._update_available_quantity(
            template.product_variant_id if template._name == 'product.template' else template,
            self.stock, qty)

    def _order(self, lines, days_ago=3):
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'date_order': fields.Datetime.now() - timedelta(days=days_ago),
        })
        dest = self.pick_type.default_location_dest_id.id or self.stock.id
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.pick_type.id,
            'location_id': self.stock.id,
            'location_dest_id': dest,
            'partner_id': self.partner.id,
            'origin': so.name,
            'move_ids': [(0, 0, {
                'product_id': p.id,
                'product_uom_qty': qty,
                'product_uom': p.uom_id.id,
                'location_id': self.stock.id,
                'location_dest_id': dest,
            }) for p, qty in lines],
        })
        picking.action_confirm()
        return so, picking

    def _mine(self, picking):
        return self.Line.search([('picking_id', '=', picking.id)])

    def test_the_twin_is_paired_both_ways(self):
        self.assertEqual(self.chi_hinge.aa_line_twin_id, self.atl_hinge)
        self.assertEqual(self.chi_hinge.product_variant_id._aa_line_twin(),
                         self.atl_hinge.product_variant_id)

    def test_variants_pair_by_their_values(self):
        size = self.env['product.attribute'].create({
            'name': 'HWL Size', 'value_ids': [(0, 0, {'name': '#10'}), (0, 0, {'name': '#12'})]})
        lines = [(0, 0, {'attribute_id': size.id, 'value_ids': [(6, 0, size.value_ids.ids)]})]
        chi = self.env['product.template'].create({
            'name': 'HWL Sized CHI', 'aa_hw_line': 'chi', 'aa_line_must_match': True,
            'attribute_line_ids': lines})
        atl = self.env['product.template'].create({
            'name': 'HWL Sized ATL', 'aa_hw_line': 'atl', 'aa_line_must_match': True,
            'attribute_line_ids': lines, 'aa_line_twin_id': chi.id})
        for variant in chi.product_variant_ids:
            twin = variant._aa_line_twin()
            self.assertEqual(twin.product_tmpl_id, atl)
            self.assertEqual(
                twin.product_template_attribute_value_ids.name,
                variant.product_template_attribute_value_ids.name)

    def test_a_short_chi_door_is_offered_atl_whole(self):
        self._stock(self.chi_hinge, 0)
        self._stock(self.chi_jamb, 50)
        self._stock(self.atl_hinge, 20)
        self._stock(self.atl_jamb, 20)
        _so, picking = self._order([
            (self.chi_hinge.product_variant_id, 4),
            (self.chi_jamb.product_variant_id, 8),
            (self.roller, 2)])
        self.Line.action_open_coverage()
        lines = self._mine(picking)
        hinge = lines.filtered(lambda l: l.product_id.product_tmpl_id == self.chi_hinge)
        jamb = lines.filtered(lambda l: l.product_id.product_tmpl_id == self.chi_jamb)
        self.assertEqual(hinge.line_to, 'atl')
        self.assertFalse(hinge.is_short)
        self.assertEqual(hinge.line_twin_id.product_tmpl_id, self.atl_hinge)
        # THE WHOLE DOOR MOVES: the jamb brackets CHI had plenty of go too.
        self.assertEqual(jamb.line_to, 'atl')
        self.assertEqual(jamb.qty_line, 8)
        roller = lines.filtered(lambda l: l.product_id == self.roller)
        self.assertFalse(roller.line_to, 'a part that fits both lines stays put')

    def test_never_half_a_door(self):
        """No ATL bottom bracket, so a door needing one cannot go ATL."""
        self._stock(self.atl_hinge, 20)
        _so, picking = self._order([
            (self.chi_hinge.product_variant_id, 4),
            (self.chi_bottom.product_variant_id, 1)])
        self.Line.action_open_coverage()
        hinge = self._mine(picking).filtered(
            lambda l: l.product_id.product_tmpl_id == self.chi_hinge)
        self.assertTrue(hinge.is_short)
        self.assertFalse(hinge.line_to)

    def test_not_offered_when_atl_cannot_cover_all_of_it(self):
        self._stock(self.atl_hinge, 2)
        _so, picking = self._order([(self.chi_hinge.product_variant_id, 4)])
        self.Line.action_open_coverage()
        hinge = self._mine(picking)
        self.assertTrue(hinge.is_short)
        self.assertFalse(hinge.line_to)

    def test_switching_swaps_the_parts_on_the_work_order(self):
        self._stock(self.atl_hinge, 20)
        self._stock(self.atl_jamb, 20)
        so, picking = self._order([
            (self.chi_hinge.product_variant_id, 4),
            (self.chi_jamb.product_variant_id, 8),
            (self.roller, 2)])
        so.aa_set_hw_line('atl')
        products = picking.move_ids.mapped('product_id')
        self.assertIn(self.atl_hinge.product_variant_id, products)
        self.assertIn(self.atl_jamb.product_variant_id, products)
        self.assertNotIn(self.chi_hinge.product_variant_id, products)
        self.assertIn(self.roller, products)
        self.assertEqual(so.aa_hw_line, 'atl')
        self.assertEqual(picking.aa_hw_line, 'atl')
        jamb = picking.move_ids.filtered(lambda m: m.product_id.product_tmpl_id == self.atl_jamb)
        self.assertEqual(jamb.product_uom_qty, 8)
        # and back again
        so.aa_set_hw_line('chi')
        self.assertIn(self.chi_hinge.product_variant_id, picking.move_ids.mapped('product_id'))

    def test_switch_refused_when_a_part_has_no_twin(self):
        so, picking = self._order([
            (self.chi_hinge.product_variant_id, 4),
            (self.chi_bottom.product_variant_id, 1)])
        with self.assertRaises(UserError):
            so.aa_set_hw_line('atl')
        self.assertIn(self.chi_hinge.product_variant_id, picking.move_ids.mapped('product_id'),
                      'all or nothing: nothing was swapped')

    def test_atl_horizontal_gets_its_angle(self):
        so, _picking = self._order([(self.roller, 1)])
        job = self.env['mrp.production'].create({
            'product_id': self.roller.id,
            'product_qty': 1,
            'origin': so.name,
            'move_raw_ids': [(0, 0, {
                'product_id': self.chi_horizontal.product_variant_id.id,
                'product_uom_qty': 2,
                'product_uom': self.chi_horizontal.uom_id.id,
            })],
        })
        job.action_confirm()
        so.aa_use_twin(self.chi_horizontal.product_variant_id.id)
        products = job.move_raw_ids.mapped('product_id')
        self.assertIn(self.atl_horizontal.product_variant_id, products)
        angle = job.move_raw_ids.filtered(lambda m: m.product_id == self.angle)
        self.assertEqual(angle.product_uom_qty, 2, 'one angle per RAW piece')

    def test_a_loose_atl_horizontal_is_offered_with_its_angle(self):
        self._stock(self.atl_horizontal, 3)
        _so, picking = self._order([(self.chi_horizontal.product_variant_id, 2)])
        self.Line.action_open_coverage()
        line = self._mine(picking)
        self.assertEqual(line.line_to, 'atl')
        self.assertFalse(line.is_short)
        data = self.Line._aa_lines_with_arrivals(line, {})
        self.assertEqual(data[0]['prep_part'], 'HWL 2x2 Angle')
