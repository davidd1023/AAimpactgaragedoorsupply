from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestNextPO(TransactionCase):
    """The Next P.O. tab: one suggestion per vendor, by lead time."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.vendor = cls.env['res.partner'].create({
            'name': 'NextPO Vendor', 'aa_lead_days': 70})
        cls.part = cls.env['product.product'].create({
            'name': 'NextPO Hinge', 'is_storable': True, 'purchase_ok': True,
            'seller_ids': [(0, 0, {'partner_id': cls.vendor.id, 'price': 2.0})],
        })
        cls.env['stock.quant']._update_available_quantity(cls.part, cls.stock, 100)
        # 90 used over the forecast window: one a day.
        cls._use(cls.part, 90)

    @classmethod
    def _use(cls, product, qty):
        customer = cls.env.ref('stock.stock_location_customers')
        move = cls.env['stock.move'].create({
            'product_id': product.id, 'product_uom_qty': qty,
            'product_uom': product.uom_id.id,
            'location_id': cls.stock.id, 'location_dest_id': customer.id,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = qty
        move.picked = True
        move._action_done()

    def _row(self, open_needs=None):
        Line = self.env['aa.order.coverage.line']
        cache = {}
        data = self.env['aa.next.po'].aa_next_po(
            open_needs or {}, lambda p: Line._aa_family(p, cache))
        for vendor in data['vendors']:
            if vendor['id'] == self.vendor.id:
                rows = [r for r in vendor['lines'] if r['id'] == self.part.id]
                return vendor, (rows[0] if rows else None)
        return None, None

    def test_order_covers_lead_time_and_next_cycle(self):
        # 1 a day x (70 lead + 70 cycle) = 140, less the 10 left on hand.
        vendor, row = self._row()
        self.assertEqual(vendor['lead'], 70)
        self.assertEqual(row['on_hand'], 10)
        self.assertEqual(row['qty'], 130)
        self.assertAlmostEqual(row['per_month'], 30.0)

    def test_open_orders_and_minimum_are_added(self):
        self.env['stock.warehouse.orderpoint'].create({
            'product_id': self.part.id, 'location_id': self.stock.id,
            'product_min_qty': 20, 'product_max_qty': 20, 'trigger': 'manual'})
        vendor, row = self._row({self.part: 15})
        self.assertEqual(row['qty'], 130 + 15 + 20)

    def test_cycle_setting_shortens_the_order(self):
        self.vendor.aa_cycle_days = 30
        vendor, row = self._row()
        self.assertEqual(row['qty'], 100 - 10)

    def test_confirmed_po_is_coming_and_draft_is_not(self):
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'order_line': [(0, 0, {'product_id': self.part.id, 'product_qty': 50})]})
        vendor, row = self._row()
        self.assertEqual(row['qty'], 130, "a draft is a suggestion, not stock")
        po.button_confirm()
        vendor, row = self._row()
        self.assertEqual(row['coming'], 50)
        self.assertEqual(row['qty'], 80)

    def test_draft_is_created_then_rewritten_not_duplicated(self):
        NextPO = self.env['aa.next.po']
        first = NextPO.aa_draft_po(self.vendor.id, [{'product_id': self.part.id, 'qty': 130}])
        second = NextPO.aa_draft_po(self.vendor.id, [{'product_id': self.part.id, 'qty': 99}])
        self.assertEqual(first['id'], second['id'])
        po = self.env['purchase.order'].browse(second['id'])
        self.assertTrue(po.aa_suggested)
        self.assertEqual(po.state, 'draft')
        self.assertEqual(po.order_line.product_qty, 99)
        self.assertEqual(po.order_line.price_unit, 2.0)
        vendor, row = self._row()
        self.assertEqual(vendor['draft']['id'], po.id)
        # Confirmed, it leaves the tab as a draft and counts as coming.
        po.button_confirm()
        vendor, row = self._row()
        self.assertFalse(vendor and vendor['draft'])
        self.assertEqual(row["qty"], 140 - 10 - 99)

    def test_parts_made_here_are_never_bought(self):
        tmpl = self.part.product_tmpl_id
        self.env['mrp.bom'].create({'product_tmpl_id': tmpl.id, 'type': 'normal'})
        vendor, row = self._row()
        self.assertIsNone(row)

    def test_board_carries_the_next_po(self):
        data = self.env['aa.order.coverage.line'].aa_board_data()
        self.assertIn('next_po', data)
        ids = {f['id'] for f in data['families']}
        for vendor in data['next_po']['vendors']:
            for row in vendor['lines']:
                self.assertIn(row['family_id'], ids)

    def test_cable_is_ordered_in_whole_reels(self):
        reel = self.env['product.product'].create({
            'name': 'NextPO 1/8 GAC (500 FT REEL)', 'is_storable': True,
            'purchase_ok': True,
            'seller_ids': [(0, 0, {'partner_id': self.vendor.id})]})
        Line = self.env['aa.order.coverage.line']
        data = self.env['aa.next.po'].aa_next_po(
            {reel: 1208}, lambda p: Line._aa_family(p, {}))
        row = [r for v in data['vendors'] for r in v['lines'] if r['id'] == reel.id][0]
        self.assertEqual(row['qty'], 1500)

    def test_boxed_parts_are_ordered_in_whole_boxes(self):
        trim = self.env['product.product'].create({
            'name': 'NextPO Trim', 'is_storable': True, 'purchase_ok': True,
            'seller_ids': [(0, 0, {
                'partner_id': self.vendor.id, 'price': 16.194, 'min_qty': 15,
                'product_name': "2in Vinyl Stop 18' Dark Brown (P5), 15 pcs/box"})]})
        Line = self.env['aa.order.coverage.line']
        data = self.env['aa.next.po'].aa_next_po(
            {trim: 17}, lambda p: Line._aa_family(p, {}))
        row = [r for v in data['vendors'] for r in v['lines'] if r['id'] == trim.id][0]
        self.assertEqual(row['qty'], 30)
