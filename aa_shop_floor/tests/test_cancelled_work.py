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

    # --- and the work already stranded, which no hook can reach -----------

    def _strand(self):
        """A job left exactly as the owner photographed it.

        BUILT THE WAY THE STATE REALLY ARISES, not by cancelling and
        un-cancelling: when the order goes, Odoo sets the job's sale line to
        null and leaves the origin naming an order that cannot be found. The
        job itself is untouched - still confirmed, with live moves - which is
        why it is still on the board and why it can still be cancelled. An
        earlier version of this fixture cancelled the order first, which
        cancelled the job's moves, and then nothing could cancel it again.
        """
        order = self._order()
        job = self._jobs(order)
        job.write({"aa_sale_line_id": False, "origin": "S09999"})

        self.assertFalse(
            self.env["sale.order"].search([("name", "=", "S09999")]),
            "the fixture's missing order is not missing")

        return job

    def test_a_job_whose_order_was_deleted_is_found(self):
        job = self._strand()

        orphans = self.env["mrp.production"]._aa_orphan_station_jobs()

        self.assertIn(job, orphans)
        self.assertFalse(job.aa_sale_line_id,
                         "the fixture is not the state he photographed")

    def test_a_job_whose_order_still_stands_is_not_touched(self):
        """THE TEST THAT MATTERS MOST HERE. Sweeping up must not take live
        work with it."""
        order = self._order()
        job = self._jobs(order)

        orphans = self.env["mrp.production"]._aa_orphan_station_jobs()

        self.assertNotIn(job, orphans)
        self.assertEqual(order.state, "sale")

    def test_a_hand_made_job_is_not_read_as_abandoned(self):
        """A manufacturing order nobody raised from a sale has no order
        behind it by nature, and is not ours to cancel."""
        product = self.env["product.product"].create({
            "name": "Hand made", "type": "consu", "is_storable": True})
        production = self.env["mrp.production"].create({
            "product_id": product.id, "product_qty": 1.0})
        production.action_confirm()

        self.assertNotIn(
            production, self.env["mrp.production"]._aa_orphan_station_jobs())

    def test_the_screen_lists_them_and_changes_nothing(self):
        job = self._strand()

        wizard = self.env["aa.shop.floor.cleanup"].create({})

        self.assertIn(job.name, wizard.report)
        self.assertEqual(wizard.job_count, 1)
        self.assertEqual(job.state, "confirmed", "looking changed something")

    def test_the_screen_deletes_work_whose_order_was_deleted(self):
        """DELETED, not cancelled. Owner, 2026-10-22: "i press delete to get
        rid of them, after that the manufacturing orders are still there" -
        a job cancelled beside an order number that answers to nothing is
        litter in the Manufacturing list."""
        job = self._strand()
        wizard = self.env["aa.shop.floor.cleanup"].create({})

        wizard.action_clear()

        self.assertFalse(job.exists(), "the job was only cancelled")
        self.assertEqual(wizard.job_count, 0)
        self.assertIn("Deleted 1", wizard.report)

    def test_the_screen_only_cancels_work_whose_order_still_stands(self):
        """A cancelled order is still there to keep the record beside, so its
        job is cancelled and kept."""
        order = self._order()
        job = self._jobs(order)
        order.write({"state": "cancel"})

        self.env["aa.shop.floor.cleanup"].create({}).action_clear()

        self.assertTrue(job.exists(), "a job was deleted out from beside its order")
        self.assertEqual(job.state, "cancel")

    def test_litter_left_by_the_earlier_fix_is_swept_up_too(self):
        """A job my own cancel hook took off the board, whose order was then
        deleted. It is off the Shop Floor already and still a row in the
        Manufacturing list naming an order that cannot be opened."""
        order = self._order()
        job = self._jobs(order)
        order._action_cancel()
        self.assertEqual(job.state, "cancel", "the fixture is not the litter")
        job.write({"aa_sale_line_id": False, "origin": "S09998"})

        self.env["aa.shop.floor.cleanup"].create({}).action_clear()

        self.assertFalse(job.exists(), "the litter was left behind")

    def test_deleting_an_order_deletes_its_work(self):
        """THE ONE HE ASKED FOR. "i am making kits in the shop, the ordering
        them, afterwards i press delete to get rid of them, after that the
        manufacturing orders are still there."

        The order is put into cancel the way the old code left it - a plain
        write, with no hook firing - so that what is being tested is the
        DELETE and not the cancel.
        """
        order = self._order()
        job = self._jobs(order)
        self.assertTrue(job, "the fixture made no job")
        order.write({"state": "cancel"})

        order.unlink()

        self.assertFalse(job.exists(), "the job outlived the order's deletion")

    def test_work_already_made_survives_the_order_being_deleted(self):
        """A job that was MADE is a record of something that happened,
        whatever became of the paperwork - so it is kept, and the delete is
        not held up by it."""
        order = self._order()
        job = self._jobs(order)
        job.write({"state": "done"})
        order.write({"state": "cancel"})

        order.unlink()

        self.assertTrue(job.exists(), "a finished job was deleted")
        self.assertEqual(job.state, "done")

    # --- the two buttons he actually presses ------------------------------

    def _work_order(self, order):
        job = self._jobs(order)
        self.assertTrue(job.workorder_ids, "the fixture made no work order")

        return job, job.workorder_ids[:1]

    def test_cancelling_the_work_order_cancels_its_station_job(self):
        """Owner, 2026-10-22: "pressing cancel on the work order doesnt work
        either", from Manufacturing > Operations > Work Orders.

        MEASURED FIRST: Odoo leaves the job in "to_close" when its last
        operation is cancelled - live, and on the board - with that cancelled
        work order still attached. Which is also why an earlier version of
        this, asking for an EMPTY work order list, could never fire."""
        order = self._order()
        job, workorder = self._work_order(order)

        workorder.action_cancel()

        self.assertEqual(workorder.state, "cancel")
        self.assertEqual(job.state, "cancel", "the job stayed on the board")
        self.assertFalse(self._on_the_board(order))

    def test_deleting_the_work_order_deletes_its_station_job(self):
        """And Delete means gone, not cancelled - off the board is not the
        same as off the Manufacturing list."""
        order = self._order()
        job, workorder = self._work_order(order)

        workorder.unlink()

        self.assertFalse(job.exists(), "the job was only cancelled")
        self.assertFalse(self._on_the_board(order))

    def test_a_job_with_work_still_on_it_is_left_alone(self):
        """Two benches, one cancelled: the job is still somebody's afternoon."""
        order = self._order()
        job, workorder = self._work_order(order)
        second = self.env["mrp.workorder"].with_context(
            aa_keep_workcenter=True).create({
                "name": "Second bench", "production_id": job.id,
                "product_uom_id": job.product_uom_id.id,
                "workcenter_id": workorder.workcenter_id.id})

        workorder.action_cancel()

        self.assertTrue(job.exists())
        self.assertNotEqual(job.state, "cancel",
                            "a job with work left on it was closed")
        self.assertEqual(second.state, "ready")

    def test_a_job_that_was_made_is_never_closed_behind_somebody(self):
        """One work order done and another cancelled: something was made, and
        that happened whatever became of the paperwork."""
        order = self._order()
        job, workorder = self._work_order(order)
        second = self.env["mrp.workorder"].with_context(
            aa_keep_workcenter=True).create({
                "name": "Second bench", "production_id": job.id,
                "product_uom_id": job.product_uom_id.id,
                "workcenter_id": workorder.workcenter_id.id})
        second.write({"state": "done"})

        workorder.action_cancel()

        self.assertTrue(job.exists())
        self.assertNotEqual(job.state, "cancel")

    def test_an_ordinary_job_is_not_closed_by_cancelling_its_operation(self):
        """Not a station job: not ours to finish off."""
        station = self.env["mrp.workcenter"].search([], limit=1) \
            or self.env["mrp.workcenter"].create({"name": "Bench"})
        product = self.env["product.product"].create({
            "name": "Hand made two", "type": "consu", "is_storable": True})
        production = self.env["mrp.production"].create({
            "product_id": product.id, "product_qty": 1.0})
        workorder = self.env["mrp.workorder"].with_context(
            aa_keep_workcenter=True).create({
                "name": "Do it", "production_id": production.id,
                "product_uom_id": production.product_uom_id.id,
                "workcenter_id": station.id})
        production.action_confirm()

        workorder.action_cancel()

        self.assertTrue(production.exists())
        self.assertNotEqual(production.state, "cancel")
