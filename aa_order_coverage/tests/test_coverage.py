from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestOrderCoverage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.pick_type = cls.warehouse.pick_type_id
        # Every open order already in the database would sit in the queue
        # ahead of ours; only our own lines are asserted on.
        Categ = cls.env['product.category']
        cls.tracks = Categ.create({'name': 'Tracks TEST'})
        cls.hinges = Categ.create({'name': 'Hinges TEST'})
        Product = cls.env['product.product']
        cls.track = Product.create({
            'name': 'Coverage Track', 'is_storable': True,
            'categ_id': cls.tracks.id})
        cls.hinge = Product.create({
            'name': 'Coverage Hinge', 'is_storable': True,
            'categ_id': cls.hinges.id})
        cls.raw = Product.create({
            'name': 'Coverage RAW Track', 'is_storable': True,
            'categ_id': cls.tracks.id})
        cls.prepared = Product.create({
            'name': 'Coverage Prepared Track', 'is_storable': True,
            'categ_id': cls.tracks.id})
        cls.partner = cls.env['res.partner'].create({'name': 'Coverage Dealer'})
        Quant = cls.env['stock.quant']
        Quant._update_available_quantity(cls.track, cls.stock, 5)
        Quant._update_available_quantity(cls.hinge, cls.stock, 100)
        Quant._update_available_quantity(cls.raw, cls.stock, 1)
        cls.Line = cls.env['aa.order.coverage.line']

    def _order(self, ref, lines, days_ago):
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'client_order_ref': ref,
            'date_order': fields.Datetime.now() - timedelta(days=days_ago),
        })
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.pick_type.id,
            'location_id': self.stock.id,
            'location_dest_id': self.pick_type.default_location_dest_id.id
                                or self.stock.id,
            'partner_id': self.partner.id,
            'origin': so.name,
            'move_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'location_id': self.stock.id,
                'location_dest_id': self.pick_type.default_location_dest_id.id
                                    or self.stock.id,
            }) for product, qty in lines],
        })
        picking.action_confirm()
        return so, picking

    def _lines(self, picking):
        return self.Line.search([('picking_id', '=', picking.id)])

    def test_first_come_first_served(self):
        """5 tracks: the oldest order takes 3, the next finds 2 and is short 1."""
        _so1, old = self._order('PO-OLD', [(self.track, 3), (self.hinge, 10)], 5)
        _so2, new = self._order('PO-NEW', [(self.track, 3), (self.hinge, 10)], 1)
        self.Line.action_open_coverage()

        old_track = self._lines(old).filtered(lambda l: l.product_id == self.track)
        new_track = self._lines(new).filtered(lambda l: l.product_id == self.track)
        self.assertFalse(old_track.is_short)
        self.assertEqual(old_track.qty_before, 5)
        self.assertTrue(new_track.is_short)
        self.assertEqual(new_track.qty_before, 2)
        self.assertEqual(new_track.qty_short, 1)
        self.assertLess(old_track.seq, new_track.seq, 'oldest order first')

        # The hinges cover both: filtering to hinges, both orders are fine.
        new_hinge = self._lines(new).filtered(lambda l: l.product_id == self.hinge)
        self.assertFalse(new_hinge.is_short)
        self.assertNotEqual(new_hinge.family_id, new_track.family_id)

    def test_family_row_names_the_first_short_order(self):
        self._order('PO-A', [(self.track, 4)], 5)
        self._order('PO-B', [(self.track, 4)], 1)
        self.Line.action_open_families()
        family = self.env['aa.order.coverage.family'].search(
            [('name', '=', 'Tracks TEST')])
        self.assertTrue(family)
        self.assertIn('PO-B', family.first_short)
        self.assertIn('Coverage Track', family.first_short_parts)
        self.assertIn('PO-A', family.covered_upto or '')

    def test_part_made_by_the_orders_own_job_is_not_counted_twice(self):
        """A prepared track is asked of the shelf as its RAW track, once."""
        so, picking = self._order('PO-PREP', [(self.prepared, 1)], 3)
        production = self.env['mrp.production'].create({
            'product_id': self.prepared.id,
            'product_qty': 1,
            'origin': so.name,
            'move_raw_ids': [(0, 0, {
                'product_id': self.raw.id,
                'product_uom_qty': 1,
                'product_uom': self.raw.uom_id.id,
            })],
        })
        production.action_confirm()
        self.Line.action_open_coverage()
        lines = self._lines(picking)
        self.assertNotIn(self.prepared, lines.mapped('product_id'))
        raw = lines.filtered(lambda l: l.product_id == self.raw)
        self.assertEqual(raw.qty_needed, 1)
        self.assertEqual(raw.source, 'prep')

    def test_each_user_has_his_own_lines(self):
        self._order('PO-U', [(self.track, 1)], 2)
        self.Line.action_open_coverage()
        mine = self.Line.search_count([('user_id', '=', self.env.uid)])
        other = self.env['res.users'].create({
            'name': 'Coverage Clerk', 'login': 'coverage_clerk',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        self.Line.with_user(other).action_open_coverage()
        self.assertEqual(
            self.Line.search_count([('user_id', '=', self.env.uid)]), mine,
            "somebody else opening the screen must not touch my figures")
        self.assertFalse(self.Line.with_user(other).search(
            [('user_id', '=', self.env.uid)]))

    def test_done_orders_are_not_listed(self):
        _so, picking = self._order('PO-DONE', [(self.hinge, 1)], 2)
        picking.action_cancel()
        self.Line.action_open_coverage()
        self.assertFalse(self._lines(picking))

    def test_the_only_menu_is_orders_to_make(self):
        """Owner: "dejemos solamente el que creamos ahora"."""
        menus = self.env['ir.ui.menu'].search(
            [('parent_id', '=', self.env.ref('stock.menu_warehouse_report').id)])
        ours = [m.name for m in menus
                if m.get_external_id().get(m.id, '').startswith('aa_order_coverage.')]
        self.assertEqual(ours, ['Orders to Make'])
        action = self.env.ref('aa_order_coverage.action_aa_order_board')
        self.assertEqual(action.tag, 'aa_order_coverage.board')

    def test_board_data_says_what_we_do_not_have(self):
        """5 tracks on the shelf, two orders wanting 3 each: 1 missing."""
        self._order('PO-B1', [(self.track, 3), (self.hinge, 10)], 5)
        self._order('PO-B2', [(self.track, 3)], 1)
        clerk = self.env['res.users'].create({
            'name': 'Board Clerk', 'login': 'board_clerk',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        data = self.Line.with_user(clerk).aa_board_data()
        track = next(p for p in data['products'] if p['id'] == self.track.id)
        self.assertEqual(track['needed'], 6)
        self.assertEqual(track['on_hand'], 5)
        self.assertEqual(track['missing'], 1)
        self.assertEqual(track['to_order'], 1)
        hinge = next(p for p in data['products'] if p['id'] == self.hinge.id)
        self.assertEqual(hinge['missing'], 0)
        # the second order is short of a track and of nothing else
        seq = {o['po']: o['seq'] for o in data['orders']}
        short = [l for l in data['lines'] if l['seq'] == seq['PO-B2'] and l['short']]
        self.assertEqual([l['product_id'] for l in short], [self.track.id])
        self.assertIn(self.tracks.name, [f['name'] for f in data['families']])


@tagged('post_install', '-at_install')
class TestCutFromLonger(TestOrderCoverage):
    """Owner, 2026-11-18: out of one length, a longer one of the same size,
    kind and colour can be cut down - but only what no order needs itself."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']
        Quant = cls.env['stock.quant']

        def raw(name, qty):
            product = Product.create({
                'name': name, 'is_storable': True, 'categ_id': cls.tracks.id})
            if qty:
                Quant._update_available_quantity(product, cls.stock, qty)
            return product
        cls.short74 = raw('9" Vertical Track RAW - 7\'4" Black', 0)
        cls.long94 = raw('9" Vertical Track RAW - 9\'4" Black', 3)
        cls.long134 = raw('9" Vertical Track RAW - 13\'4" Black', 5)
        cls.white94 = raw('9" Vertical Track RAW - 9\'4" White', 10)
        cls.horiz = raw('9" Horizontal Track RAW - 9\'6" Black', 10)

    def _line(self, picking, product):
        return self._lines(picking).filtered(lambda l: l.product_id == product)

    def test_cut_from_shortest_spare_longer_piece(self):
        # Another order needs 2 of the 9'4": only 1 of the 3 is spare.
        _so0, other = self._order('PO-NEEDS-94', [(self.long94, 2)], 9)
        _so1, first = self._order('PO-CUT-1', [(self.short74, 2)], 5)
        _so2, second = self._order('PO-CUT-2', [(self.short74, 6)], 1)
        self.Line.action_open_coverage()

        self.assertFalse(self._line(other, self.long94).is_short)
        one = self._line(first, self.short74)
        # The 1 spare 9'4" (shortest that fits); one line takes one longer length.
        self.assertEqual(one.swap_product_id, self.long94)
        self.assertEqual(one.qty_swap, 1)
        self.assertTrue(one.is_short, 'one piece still missing on this line')
        two = self._line(second, self.short74)
        self.assertEqual(two.swap_product_id, self.long134)
        self.assertEqual(two.qty_swap, 5)
        self.assertTrue(two.is_short)
        self.assertEqual(two.qty_short, 6, 'the shortage of the part itself stays')

    def test_never_another_colour_or_kind(self):
        _so, order = self._order('PO-WHITE', [(self.short74, 1)], 1)
        self.long94.stock_quant_ids.sudo().unlink()
        self.long134.stock_quant_ids.sudo().unlink()
        self.Line.action_open_coverage()
        line = self._line(order, self.short74)
        self.assertFalse(line.swap_product_id)
        self.assertTrue(line.is_short)

    def test_board_shows_the_cut(self):
        _so, order = self._order('PO-BOARD', [(self.short74, 1)], 1)
        data = self.Line.aa_board_data()
        seq = self._line(order, self.short74).seq
        row = [l for l in data['lines'] if l['seq'] == seq and l['product_id'] == self.short74.id][0]
        self.assertEqual(row['short'], 0, 'covered by the longer piece')
        self.assertEqual(row['missing'], 1)
        self.assertEqual(row['swap_qty'], 1)
        self.assertEqual(row['swap_length'], "9'4\"")


@tagged('post_install', '-at_install')
class TestThroughShopFloor(TestOrderCoverage):
    """Owner, 2026-11-18: an order already through the Shop Floor (942) is
    not one to make - but its box holds its parts."""

    def test_finished_order_hidden_and_its_parts_set_aside(self):
        _so1, done = self._order('PO-942', [(self.track, 3)], 9)
        done.message_post(body='All stations are done, but not everything on this '
                               'work order is in stock yet, so it was not sent to Dispatch.')
        _so2, waiting = self._order('PO-NEXT', [(self.track, 3)], 1)
        self.Line.action_open_coverage()

        self.assertFalse(self._lines(done), 'already through the Shop Floor')
        line = self._lines(waiting).filtered(lambda l: l.product_id == self.track)
        # 5 tracks, 3 of them in the finished order's box.
        self.assertEqual(line.qty_before, 2)
        self.assertEqual(line.qty_short, 1)
        data = self.Line.aa_board_data()
        self.assertNotIn('PO-942', [o['po'] for o in data['orders']])


@tagged('post_install', '-at_install')
class TestPaintGalvanized(TestOrderCoverage):
    """Owner, 2026-11-19: Mill Finish = Galvanized, and anything with a
    colour can be painted to finish an order; the paint P.O. gives the date."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']
        Quant = cls.env['stock.quant']

        def raw(name, qty):
            product = Product.create({
                'name': name, 'is_storable': True, 'categ_id': cls.tracks.id})
            if qty:
                Quant._update_available_quantity(product, cls.stock, qty)
            return product
        cls.black = raw('8" Vertical Track RAW - 7\'4" Black', 0)
        cls.galv = raw('8" Vertical Track RAW - 7\'4" Galvanized', 5)
        cls.painter = cls.env['res.partner'].create({
            'name': 'Coverage Test Painter', 'is_company': True, 'aa_paints_parts': True})

    def _line(self, picking, product):
        return self._lines(picking).filtered(lambda l: l.product_id == product)

    def test_twin_by_name(self):
        from odoo.addons.aa_order_coverage.models.paint import galvanized_twin
        self.assertEqual(galvanized_twin(self.black), self.galv)
        self.assertFalse(galvanized_twin(self.galv), 'Galvanized is not painted again')

    def test_spare_galvanized_is_suggested_and_others_keep_theirs(self):
        _s0, needs_galv = self._order('PO-GALV', [(self.galv, 2)], 9)
        _s1, first = self._order('PO-PAINT-1', [(self.black, 2)], 5)
        _s2, second = self._order('PO-PAINT-2', [(self.black, 4)], 1)
        self.Line.action_open_coverage()
        self.assertFalse(self._line(needs_galv, self.galv).is_short)
        one = self._line(first, self.black)
        self.assertEqual((one.paint_product_id, one.qty_paint), (self.galv, 2))
        self.assertTrue(one.is_short, 'still has to go to the painter')
        two = self._line(second, self.black)
        self.assertEqual(two.qty_paint, 1, '5 Galvanized, 2 needed as they are, 2 painted first')

    def test_paint_po_covers_first_and_receiving_takes_the_galvanized(self):
        _s1, order = self._order('PO-PAINT-3', [(self.black, 2)], 5)
        action = self.Line.aa_paint_po(self.black.id, 2)
        po = self.env['purchase.order'].browse(action['res_id'])
        self.assertEqual(po.partner_id, self.painter)
        self.Line.action_open_coverage()
        line = self._line(order, self.black)
        self.assertFalse(line.qty_paint, 'already at the painter: not suggested twice')
        po.button_confirm()
        picking = po.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        self.assertEqual(self.black.qty_available, 2)
        self.assertEqual(self.galv.qty_available, 3, 'the two painted came off the Galvanized')
