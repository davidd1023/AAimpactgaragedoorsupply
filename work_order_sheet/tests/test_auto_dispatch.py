from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAutoDispatch(TransactionCase):
    """The last station finishing sends the order to Dispatch on its own
    (owner, 2026-10-19)."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.warehouse.delivery_steps = "pick_ship"
        self.part = self.env["product.product"].create({
            "name": "Boxed part", "type": "consu", "is_storable": True})
        self.made = self.env["product.product"].create({
            "name": "Station-made part", "type": "consu", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(
            self.part, self.warehouse.lot_stock_id, 10)
        partner = self.env["res.partner"].create({"name": "Auto dispatch customer"})
        self.order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [(0, 0, {"product_id": self.part.id, "product_uom_qty": 2})],
        })
        self.order.action_confirm()
        self.work_order = self.order._aa_work_order_transfers()

    def _production(self):
        production = self.env["mrp.production"].create({
            "product_id": self.made.id, "product_qty": 1, "origin": self.order.name})
        production.action_confirm()
        production.qty_producing = 1
        return production

    def _outgoing(self):
        return self.env["stock.picking"].search([
            ("aa_wo_number", "=", self.order.aa_wo_number),
            ("picking_type_code", "=", "outgoing")])

    def test_last_station_done_validates_the_work_order(self):
        first, last = self._production(), self._production()
        first.button_mark_done()
        self.assertNotEqual(self.work_order.state, "done", "one station still working")

        last.button_mark_done()
        self.assertEqual(self.work_order.state, "done")
        self.assertTrue(self._outgoing(), "the Dispatch is there")
        self.assertIn("sent to Dispatch", self.work_order.message_ids[0].body)

    def test_not_in_stock_stays_and_says_why(self):
        self.work_order.do_unreserve()
        self.env["stock.quant"]._update_available_quantity(
            self.part, self.warehouse.lot_stock_id, -10)
        production = self._production()
        production.button_mark_done()

        self.assertEqual(production.state, "done", "the station's job still finishes")
        self.assertNotEqual(self.work_order.state, "done")
        self.assertIn("is in stock yet", self.work_order.message_ids[0].body)
