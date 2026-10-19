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
