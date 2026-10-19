"""THE BOARD HEARS ABOUT A CANCEL.

The owner, 2026-10-19: "when i cancel an order in manufacturing it doesnt
automatically cancel it in shop floor". The cancel itself always worked - these
tests say so, in every state a job can be cancelled from - and what was missing
was anybody telling the tablet, which loads its records once and then only
reloads when something inside it asks.
"""

from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class ShopFloorLiveCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.station = self.env["mrp.workcenter"].search(
            [("name", "!=", "Pending Assignment")], limit=1) \
            or self.env["mrp.workcenter"].create({"name": "Springs"})
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True})

    def _job(self, start=False):
        production = self.env["mrp.production"].create({
            "product_id": self.product.id, "product_qty": 1.0,
            "origin": "S00123"})
        workorder = self.env["mrp.workorder"].with_context(
            aa_keep_workcenter=True).create({
                "name": "Make it", "production_id": production.id,
                "product_uom_id": production.product_uom_id.id,
                "workcenter_id": self.station.id})
        production.action_confirm()

        if start:
            workorder.button_start()

        return production, workorder

    def _capture(self):
        """What was sent to whom, as a list.

        NOT bus.bus RECORDS. Odoo writes notifications in a post-commit hook,
        so in a test - which rolls back and never commits - the table stays
        empty however correct the code is. My first three tests asserted on
        that table and failed for a reason that had nothing to do with the
        thing being tested. What matters is that this code asked, and of whom.
        """
        sent = []
        Partner = type(self.env["res.partner"])
        original = Partner._bus_send

        def spy(records, notification_type, message, **kwargs):
            sent.append((records, notification_type))

            return original(records, notification_type, message, **kwargs)

        patcher = patch.object(Partner, "_bus_send", spy)
        patcher.start()
        self.addCleanup(patcher.stop)

        return sent

    # --- the cancel itself ---------------------------------------------------

    def test_cancelling_a_job_cancels_its_work_orders(self):
        """Said out loud because it is the thing that was suspected and is not
        in fact broken - in any state a job can be cancelled from."""
        for started in (False, True):
            production, workorder = self._job(start=started)
            production.action_cancel()

            with self.subTest(started=started):
                self.assertEqual(production.state, "cancel")
                self.assertEqual(workorder.state, "cancel")

    def test_nothing_of_a_cancelled_order_is_left_on_the_board(self):
        production, _workorder = self._job()
        production.action_cancel()
        live = self.env["mrp.workorder"].search([
            ("production_id.origin", "=", "S00123"),
            ("state", "not in", ("done", "cancel")),
        ])

        self.assertFalse(live)

    # --- and the board being told about it ------------------------------------

    def test_cancelling_tells_the_shop_floor_to_look_again(self):
        """THE HALF THAT WAS MISSING. Without this the tablet shows the
        cancelled card until somebody presses Reload Data."""
        production, _workorder = self._job()
        sent = self._capture()
        production.action_cancel()

        self.assertTrue(sent, "nobody told the Shop Floor")
        self.assertEqual({kind for _to, kind in sent},
                         {"aa_shop_floor_changed"})

    def test_cancelling_one_work_order_tells_it_too(self):
        _production, workorder = self._job()
        sent = self._capture()
        workorder.action_cancel()

        self.assertTrue(sent)

    def test_it_goes_to_the_floor_and_not_to_a_channel_anybody_can_guess(self):
        """Odoo warns against made-up channel names: a name somebody can guess
        is a name somebody can listen on. Every user is already subscribed to
        their own, so this goes to the shop floor's own people."""
        production, _workorder = self._job()
        sent = self._capture()
        production.action_cancel()

        told = self.env["res.partner"]

        for recipients, _kind in sent:
            self.assertEqual(recipients._name, "res.partner")
            told |= recipients

        floor = self.env.ref("mrp.group_mrp_user").sudo().user_ids.partner_id
        self.assertTrue(told & floor, "the floor's own users were not told")

    def test_a_cancel_still_goes_through_if_the_bus_will_not(self):
        """A notification is a courtesy. A cancel that worked must not be
        undone because a websocket was unhappy."""
        production, workorder = self._job()
        original = type(self.env["res.partner"])._bus_send

        def explode(records, *args, **kwargs):
            raise ValueError("the bus fell over")

        type(self.env["res.partner"])._bus_send = explode

        try:
            production.action_cancel()
        finally:
            type(self.env["res.partner"])._bus_send = original

        self.assertEqual(production.state, "cancel")
        self.assertEqual(workorder.state, "cancel")
