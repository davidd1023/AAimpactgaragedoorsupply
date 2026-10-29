from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDispatchedButton(TransactionCase):
    """The Dispatched button (owner, 2026-10-19): one press validates the
    delivery and records who sent it out and when."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.warehouse.delivery_steps = "ship_only"
        self.product = self.env["product.product"].create({
            "name": "Dispatch test part", "type": "consu", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 10)
        self.partner = self.env["res.partner"].create({"name": "Dispatch customer"})
        self.order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 2})],
        })
        self.order.action_confirm()
        self.delivery = self.order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing")
        self.delivery.action_assign()

    def _sign(self, tick_all=True):
        self.delivery.write({"dispatch_signed_on": fields.Datetime.now(),
                             "dispatch_signed_by": "Customer"})
        self.delivery._dispatch_lines().write({"dispatch_received": tick_all})

    def test_signed_in_full_is_clean_and_dispatches(self):
        self._sign()
        self.assertTrue(self.delivery.aa_dispatch_clean)
        self.delivery.action_aa_dispatched()

        self.assertEqual(self.delivery.state, "done")
        self.assertEqual(self.delivery.aa_dispatched_by, self.env.user)
        self.assertTrue(self.delivery.aa_dispatched_on)
        self.assertEqual(self.delivery.move_ids.quantity, 2)
        self.assertIn("Dispatched by", self.order.message_ids[0].body)

    def test_unsigned_is_not_clean_but_can_still_go(self):
        self.assertFalse(self.delivery.aa_dispatch_clean)
        self.delivery.action_aa_dispatched()
        self.assertEqual(self.delivery.state, "done")
        self.assertIn("had not signed", self.delivery.message_ids[0].body)

    def test_an_item_not_ticked_is_not_clean(self):
        self._sign(tick_all=False)
        self.assertFalse(self.delivery.aa_dispatch_clean)

    def test_only_a_ready_delivery(self):
        self.delivery.do_unreserve()
        with self.assertRaises(UserError):
            self.delivery.action_aa_dispatched()


@tagged("post_install", "-at_install")
class DispatchWithoutInventoryCase(TransactionCase):
    """SENT FOR THE RECORD, WITHOUT USING ANY STOCK.

    Owner, 2026-10-29: *"can you do the dispatch with no inventory
    adjustment ... this is only for orders that used no actual inventory and
    is only to be used for records or testing, not for real orders."*

    Odoo will not let a transfer be Done while moving nothing - its own sanity
    check says so - and the two obvious ways round it were measured before any
    of this was written: zeroing the quantities CANCELS the moves, and
    dispatching with an empty rack simply takes the quant negative. So every
    line is delivered to the location it came from: the same quant in and out,
    which cancels exactly.
    """

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.partner = self.env["res.partner"].create({"name": "A Dealer"})
        self.product = self.env["product.product"].create({
            "name": "A door part", "type": "consu", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 50)

    def _on_hand(self):
        return self.product.with_context(
            location=self.warehouse.lot_stock_id.id).qty_available

    def _delivery(self, qty=5):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": qty})]})
        order.action_confirm()
        # HIS WAREHOUSE DELIVERS IN TWO STEPS: the outgoing transfer only
        # exists once the internal pick is validated.
        pick = order.picking_ids.filtered(
            lambda p: p.picking_type_code == "internal")

        for move in pick.move_ids:
            move.quantity = move.product_uom_qty

        pick.button_validate()
        order.invalidate_recordset()
        out = order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing")[:1]
        out.action_assign()

        return order, out

    # --- the sentence he wrote ------------------------------------------------

    def test_it_is_dispatched_and_no_stock_moves(self):
        """THE ONE THAT SETTLES IT."""
        order, picking = self._delivery()
        before = self._on_hand()
        everywhere = self.product.qty_available

        picking._aa_dispatch_without_stock()
        self.product.invalidate_recordset()

        self.assertEqual(picking.state, "done")
        self.assertEqual(self._on_hand(), before, "stock moved")
        self.assertEqual(self.product.qty_available, everywhere)
        self.assertTrue(picking.aa_dispatched_on)
        self.assertEqual(picking.aa_dispatched_by, self.env.user)

    def test_the_order_still_reads_as_delivered(self):
        """It is for RECORDS, so the record has to be complete."""
        order, picking = self._delivery(qty=5)

        picking._aa_dispatch_without_stock()
        order.invalidate_recordset()

        self.assertEqual(order.order_line.qty_delivered, 5)

    def test_the_chatter_says_no_inventory_was_used(self):
        """A transfer reading Done while the shelf never moved is a lie
        unless somebody wrote it down."""
        _order, picking = self._delivery()

        picking._aa_dispatch_without_stock()

        said = "\n".join(picking.message_ids.mapped("body"))

        self.assertIn("WITHOUT USING INVENTORY", said)

    def test_every_line_is_delivered_to_where_it_came_from(self):
        """The mechanism, asserted rather than assumed: same quant in and
        out, so the decrement and the increment are the same number."""
        _order, picking = self._delivery()

        picking._aa_dispatch_without_stock()

        for line in picking.move_line_ids:
            self.assertEqual(line.location_dest_id, line.location_id)

    # --- what it refuses ------------------------------------------------------

    def test_a_transfer_already_settled_is_left_alone(self):
        _order, picking = self._delivery()
        picking.action_cancel()

        self.assertFalse(picking._aa_dispatch_without_stock())
        self.assertEqual(picking.state, "cancel")

    def test_one_awkward_transfer_does_not_abandon_the_rest(self):
        """He had THIRTY ticked in the screenshot."""
        _one, first = self._delivery()
        _two, second = self._delivery()
        second.action_cancel()
        wizard = self.env["aa.dispatch.no.stock"].with_context(
            active_ids=(first | second).ids).create({})

        wizard.action_confirm()

        self.assertEqual(first.state, "done")
        self.assertEqual(second.state, "cancel")

    # --- the warning and where it lives --------------------------------------

    def test_the_wizard_carries_his_warning(self):
        _order, picking = self._delivery()
        wizard = self.env["aa.dispatch.no.stock"].with_context(
            active_ids=picking.ids).create({})

        self.assertIn("no actual inventory", wizard.warning)
        self.assertIn("not for real orders", wizard.warning)
        self.assertEqual(wizard.to_do_count, 1)

    def test_it_counts_the_ones_it_will_not_touch(self):
        _one, first = self._delivery()
        _two, second = self._delivery()
        second.action_cancel()

        wizard = self.env["aa.dispatch.no.stock"].with_context(
            active_ids=(first | second).ids).create({})

        self.assertEqual(wizard.to_do_count, 1)
        self.assertEqual(wizard.settled_count, 1)

    def test_it_is_in_the_actions_menu_for_stock_managers_only(self):
        action = self.env.ref("work_order_sheet.action_aa_dispatch_no_stock")

        self.assertEqual(action.binding_model_id.model, "stock.picking")
        self.assertIn("list", action.binding_view_types)
        self.assertEqual(action.group_ids,
                         self.env.ref("stock.group_stock_manager"))

    def test_opening_it_with_nothing_chosen_says_so(self):
        with self.assertRaises(UserError):
            self.env["aa.dispatch.no.stock"].with_context(
                active_ids=[]).create({})
