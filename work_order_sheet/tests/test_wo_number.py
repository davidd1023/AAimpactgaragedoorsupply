from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWorkOrderNumber(TransactionCase):
    """W/O # (owner, 2026-10-19): one number per order, given at confirmation,
    and the order's Work Order transfer is called by it."""

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.warehouse.delivery_steps = "pick_ship"
        self.partner = self.env["res.partner"].create({"name": "W/O customer"})
        self.product = self.env["product.product"].create({
            "name": "W/O test part", "type": "consu", "is_storable": True})

    def _order(self):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1})],
        })

    def _number(self, text):
        return int(text.replace("W/O #", ""))

    def test_a_quotation_has_no_number(self):
        self.assertFalse(self._order().aa_wo_number)

    def test_confirming_gives_the_next_number(self):
        first, second = self._order(), self._order()
        second.action_confirm()
        first.action_confirm()

        self.assertTrue(second.aa_wo_number.startswith("W/O #"), second.aa_wo_number)
        # In the order they were CONFIRMED, not the order they were opened.
        self.assertEqual(self._number(first.aa_wo_number), self._number(second.aa_wo_number) + 1)

    def test_confirming_twice_keeps_the_number(self):
        order = self._order()
        order.action_confirm()
        number = order.aa_wo_number
        order._aa_assign_wo_number()
        self.assertEqual(order.aa_wo_number, number)

    def test_every_transfer_carries_it_and_the_work_order_is_called_by_it(self):
        order = self._order()
        order.action_confirm()

        self.assertTrue(order.picking_ids)
        for picking in order.picking_ids:
            self.assertEqual(picking.aa_wo_number, order.aa_wo_number)

        work_order = order._aa_work_order_transfers()
        self.assertEqual(len(work_order), 1)
        self.assertEqual(work_order.name, order.aa_wo_number)
