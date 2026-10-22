"""WORK MUST NOT OUTLIVE THE THING IT WAS FOR.

The owner, 2026-10-22: "deleted orders still go to shop floor... if i delete
the work order in manufacturing, the assignments in shop floor are still
there", and then the diagnosis that turned out to be right: "the work order
creates a couple of manufacturing order. so maybe even though the work order
gets deleted the manufacturing order sticks around."

Two holes, one principle. Confirming an order raises a manufacturing order for
every spring, kit and cable on it; nothing took them away again.

  * Cancelling the order left them standing. Odoo cancels the order's
    TRANSFERS by itself and has never had an opinion about manufacturing
    raised from a sale. And since Odoo refuses to delete a confirmed order
    until it is cancelled, this is the deleted-order case as well.
  * Deleting a work order left its manufacturing order standing, in state
    confirmed, and the Shop Floor shows every order that is not done or
    cancelled - so the card stayed. An earlier fix told the tablet to look
    again, which did not help: what it looked at was still there.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class WorkOutlivingItsOrderCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Floor Test"})
        # "hardware kit" in the name is what aa_shop_floor reads to decide a
        # line is packed at a bench (is_hardware_kit).
        self.kit = self.env["product.template"].create({
            "name": "Test Hardware Kit", "type": "consu", "is_storable": True,
            "list_price": 100.0, "sale_ok": True})

    def _order(self, quantity=2.0):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.kit.product_variant_id.id,
                "product_uom_qty": quantity})],
        })
        order.action_confirm()

        return order

    def _jobs(self, order):
        return self.env["mrp.production"].search(
            [("aa_sale_line_id", "in", order.order_line.ids)])

    def _on_the_board(self, order):
        """What the Shop Floor would show: anything not done or cancelled."""
        return self.env["mrp.production"].search([
            ("aa_sale_line_id", "in", order.order_line.ids),
            ("state", "not in", ("done", "cancel")),
        ])

    # --- confirming makes the work, which is correct ----------------------

    def test_confirming_an_order_puts_a_job_on_the_floor(self):
        """Said out loud because it is the half that already worked, and the
        half everything below is about taking away again."""
        order = self._order()

        jobs = self._jobs(order)

        self.assertTrue(jobs, "the fixture made no station job")
        self.assertEqual(jobs.aa_station_kind, "kit")
        self.assertEqual(jobs.state, "confirmed")
        self.assertTrue(jobs.workorder_ids, "a station job with no bench job")

    # --- cancelling the order --------------------------------------------

    def test_cancelling_the_order_takes_its_work_off_the_board(self):
        order = self._order()
        jobs = self._jobs(order)

        order._action_cancel()

        self.assertEqual(jobs.state, "cancel", "the job outlived its order")
        self.assertFalse(self._on_the_board(order))

    def test_cancelling_says_so_on_the_order(self):
        """So that somebody reading the order later knows why the floor went
        quiet, rather than wondering whether it ever had work."""
        order = self._order()
        job = self._jobs(order)
        before = len(order.message_ids)

        order._action_cancel()

        said = "".join(m.body or "" for m in order.message_ids[:len(order.message_ids) - before])
        self.assertIn("Shop Floor work stopped", said)
        self.assertIn(job.name, said)

    def test_work_already_finished_is_left_alone(self):
        """A job that is done is a record of something that happened, and
        cancelling it would be rewriting history."""
        order = self._order()
        job = self._jobs(order)
        job.write({"state": "done"})

        order._action_cancel()

        self.assertEqual(job.state, "done")

    def test_an_order_cancelled_twice_does_not_complain(self):
        order = self._order()
        order._action_cancel()

        order._action_cancel()

        self.assertEqual(self._jobs(order).state, "cancel")

    # --- deleting the work order -----------------------------------------

    def test_deleting_the_only_work_order_cancels_its_station_job(self):
        """HIS OWN DIAGNOSIS. The manufacturing order was sticking around."""
        order = self._order()
        job = self._jobs(order)

        job.workorder_ids.unlink()

        self.assertTrue(job.exists(), "the job was deleted, not cancelled")
        self.assertEqual(job.state, "cancel", "the job stayed on the board")
        self.assertFalse(self._on_the_board(order))

    def test_an_ordinary_manufacturing_order_keeps_its_own_counsel(self):
        """One operation deleted off a route is a change to the route, not the
        end of the job - so a manufacturing order that is not one of this
        module's station jobs is not cancelled from under somebody."""
        station = self.env["mrp.workcenter"].search([], limit=1) \
            or self.env["mrp.workcenter"].create({"name": "Bench"})
        product = self.env["product.product"].create({
            "name": "Hand made thing", "type": "consu", "is_storable": True})
        production = self.env["mrp.production"].create({
            "product_id": product.id, "product_qty": 1.0})
        workorder = self.env["mrp.workorder"].with_context(
            aa_keep_workcenter=True).create({
                "name": "Do it", "production_id": production.id,
                "product_uom_id": production.product_uom_id.id,
                "workcenter_id": station.id})
        production.action_confirm()

        workorder.unlink()

        self.assertEqual(production.state, "confirmed")
        self.assertFalse(production.aa_station_kind)
