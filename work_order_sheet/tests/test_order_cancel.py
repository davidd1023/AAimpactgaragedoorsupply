"""CANCELLING AN ORDER THAT HAS ALREADY BEEN PAID.

The owner, 2026-10-19: "Right now there is no defined process for this" - a
button that takes the order off the Shop Floor, puts the goods back and refunds
through Stripe.

Three decisions he made when asked: the full amount is filled in but CAN be
changed (a restocking fee, a part cancellation); it works AFTER the order has
gone out, raising a return rather than pretending the goods are back; and it
does NOT touch a posted invoice - it says a credit note is needed and leaves
the ledger to an accountant.

STRIPE IS NOT INSTALLED HERE, and these tests do not pretend otherwise. What
is tested is the thing this code actually does: ask a payment transaction for
its money back through whatever provider took it. The refund path is driven
with a provider that supports refunds, and the dealer-account path - which
cannot be refunded and must say so - is driven with the one that does not.
"""

from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class OrderCancelCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.customer = self.env["res.partner"].create({
            "name": "Hector the Fitter", "email": "hector@example.com"})
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 100.0})
        self.station = self.env["mrp.workcenter"].search([], limit=1) \
            or self.env["mrp.workcenter"].create({"name": "Springs"})
        self.env.user.group_ids = [
            (4, self.env.ref("sales_team.group_sale_manager").id)]

    # --- the order, its jobs, its money --------------------------------------

    def _order(self, quantity=1):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": quantity})],
        })
        order.action_confirm()

        return order

    def _job(self, order, state="confirmed"):
        """A Shop Floor job of this order, found the way the shop finds them."""
        production = self.env["mrp.production"].create({
            "product_id": self.product.id,
            "product_qty": 1.0,
            "origin": order.name,
        })
        self.env["mrp.workorder"].create({
            "name": "Wind it",
            "production_id": production.id,
            "product_uom_id": production.product_uom_id.id,
            "workcenter_id": self.station.id,
        })

        if state == "confirmed":
            production.action_confirm()

        return production

    def _provider(self, refundable=True):
        """A payment provider that can, or cannot, give money back.

        The shop takes money two ways: a card (which can be refunded) and a
        dealer account (which cannot). Both have to be handled and only one of
        them can be.
        """
        provider = self.env["payment.provider"].search(
            [("code", "=", "custom")], limit=1)
        self.assertTrue(provider, "no payment provider to test with")
        # A DISABLED PROVIDER REFUSES EVERY REQUEST, which is right of it and
        # was wrong of my fixture: the provider has to be live for a refund to
        # be asked of it at all.
        provider.sudo().state = "test"

        # support_refund IS COMPUTED AND NOT STORED, so writing it - which is
        # what I did first - lasts only until the next cache invalidation, and
        # the order then quietly became refundable again halfway through the
        # procedure. The compute itself is patched instead, which survives.
        Provider = type(provider)
        original = Provider._compute_feature_support_fields
        wanted = "partial" if refundable else False

        def patched(records):
            original(records)

            for record in records:
                if record.id == provider.id:
                    record.support_refund = wanted

        patcher = patch.object(
            Provider, "_compute_feature_support_fields", patched)
        patcher.start()
        self.addCleanup(patcher.stop)
        provider.invalidate_recordset(["support_refund"])

        return provider

    def _paid(self, order, amount=None, refundable=True):
        """Money taken against the order, as a provider would record it."""
        provider = self._provider(refundable=refundable)
        transaction = self.env["payment.transaction"].sudo().create({
            "provider_id": provider.id,
            "payment_method_id": provider.payment_method_ids[:1].id
            or self.env.ref("payment.payment_method_unknown").id,
            "amount": amount if amount is not None else order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_id": self.customer.id,
            "reference": "TEST-%s" % order.name,
            "state": "done",
            "operation": "online_redirect",
            "sale_order_ids": [(6, 0, order.ids)],
        })

        return transaction

    def _wizard(self, order):
        return self.env["aa.order.cancel"].create({"order_id": order.id})

    # --- what the dialog promises --------------------------------------------

    def test_the_dialog_says_what_it_will_do(self):
        """THE DIALOG IS THE PROCEDURE. "Right now there is no defined process
        for this" - so it is written out, in the order it happens, before
        anything is pressed."""
        order = self._order()
        job = self._job(order)
        self._paid(order)
        plan = self._wizard(order).plan

        self.assertIn(job.name, plan, "it does not say what comes off the floor")
        self.assertIn("Shop Floor", plan)
        self.assertIn("Refund", plan)
        self.assertIn("Cancel the order itself", plan)

    def test_the_full_amount_is_filled_in(self):
        order = self._order()
        self._paid(order, amount=755.22)
        wizard = self._wizard(order)

        self.assertEqual(wizard.amount_paid, 755.22)
        self.assertEqual(wizard.amount_refund, 755.22)
        self.assertTrue(wizard.can_refund)

    # --- 1. off the Shop Floor -----------------------------------------------

    def test_the_jobs_come_off_the_shop_floor(self):
        """Nobody winds a spring for an order that no longer exists."""
        order = self._order()
        job = self._job(order)
        self._paid(order)
        self._wizard(order).action_cancel_and_refund()

        self.assertEqual(job.state, "cancel")

    def test_a_finished_job_is_left_alone(self):
        """It already made something. What happens to that is the return, not
        a cancellation that cannot happen anyway."""
        order = self._order()
        job = self._job(order)
        job.state = "done"
        self._paid(order)
        self._wizard(order).action_cancel_and_refund()

        self.assertEqual(job.state, "done")

    # --- 2. the goods go back ------------------------------------------------

    def test_transfers_that_have_not_happened_are_cancelled(self):
        order = self._order()
        self._paid(order)
        pickings = order.picking_ids
        self.assertTrue(pickings, "the order made no transfer")
        self._wizard(order).action_cancel_and_refund()

        self.assertEqual(set(pickings.mapped("state")), {"cancel"})

    def test_a_delivered_order_gets_a_return_raised(self):
        """The owner's own choice: it works after the goods have gone, and
        raises a return rather than claiming they are already back."""
        order = self._order()
        self._paid(order)
        picking = order.picking_ids[:1]
        self.env["stock.quant"]._update_available_quantity(
            self.product, picking.location_id, 10.0)
        picking.action_assign()

        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        picking.button_validate()
        self.assertEqual(picking.state, "done")

        before = self.env["stock.picking"].search([])
        self._wizard(order).action_cancel_and_refund()
        raised = self.env["stock.picking"].search([]) - before

        self.assertTrue(raised, "no return was raised for goods already moved")
        self.assertNotEqual(raised[0].state, "done",
                            "stock must not be said to be back before it is")

    # --- 3. the money --------------------------------------------------------

    def test_the_money_goes_back_through_whoever_took_it(self):
        order = self._order()
        transaction = self._paid(order)
        self._wizard(order).action_cancel_and_refund()

        refunds = self.env["payment.transaction"].sudo().search(
            [("source_transaction_id", "=", transaction.id)])
        self.assertTrue(refunds, "no refund was asked for")
        self.assertEqual(refunds.operation, "refund")
        self.assertEqual(abs(refunds.amount), order.amount_total)

    def test_a_part_refund_sends_only_that(self):
        """A restocking fee, or a part cancellation."""
        order = self._order()
        transaction = self._paid(order, amount=100.0)
        wizard = self._wizard(order)
        wizard.amount_refund = 75.0
        wizard.action_cancel_and_refund()

        refunds = self.env["payment.transaction"].sudo().search(
            [("source_transaction_id", "=", transaction.id)])
        self.assertEqual(abs(refunds.amount), 75.0)

    def test_more_than_was_taken_is_refused(self):
        order = self._order()
        self._paid(order, amount=100.0)
        wizard = self._wizard(order)
        wizard.amount_refund = 150.0

        with self.assertRaises(UserError):
            wizard.action_cancel_and_refund()

        self.assertNotEqual(order.state, "cancel",
                            "it must not cancel the order and then refuse")

    def test_a_dealer_account_says_so_instead_of_pretending(self):
        """There is no provider holding the money, so there is nothing to ask
        for it back. The order is still cancelled and the floor still cleared -
        somebody pays it back by hand."""
        order = self._order()
        self._job(order)
        self._paid(order, refundable=False)
        wizard = self._wizard(order)

        self.assertFalse(wizard.can_refund)
        self.assertEqual(wizard.amount_paid, 0.0)
        self.assertIn("by hand", wizard.plan)
        wizard.action_cancel_and_refund()

        self.assertEqual(order.state, "cancel")
        self.assertIn("by hand", order.message_ids[0].body)

    def test_an_unpaid_order_cancels_with_nothing_to_refund(self):
        order = self._order()
        wizard = self._wizard(order)

        self.assertIn("nothing to refund", wizard.plan)
        wizard.action_cancel_and_refund()
        self.assertEqual(order.state, "cancel")

    # --- 4. the order, and the ledger ----------------------------------------

    def test_the_order_is_cancelled_last(self):
        order = self._order()
        self._paid(order)
        self._wizard(order).action_cancel_and_refund()

        self.assertEqual(order.state, "cancel")

    def test_a_posted_invoice_is_reported_and_not_touched(self):
        """THE LEDGER IS NOT A BUTTON'S BUSINESS (owner, 2026-10-19). The
        credit note is named as needed and left for an accountant."""
        order = self._order()
        self._paid(order)
        order._create_invoices()
        invoice = order.invoice_ids[:1]
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

        wizard = self._wizard(order)
        self.assertIn(invoice.name, wizard.plan)
        self.assertIn("credit note", wizard.plan)
        wizard.action_cancel_and_refund()

        self.assertEqual(invoice.state, "posted", "the ledger was touched")
        self.assertIn("credit note", order.message_ids[0].body)
        self.assertIn(invoice.name, order.message_ids[0].body)

    def test_the_whole_procedure_is_written_on_the_order(self):
        """So the next person to look knows what was done, by whom and why."""
        order = self._order()
        self._job(order)
        self._paid(order)
        wizard = self._wizard(order)
        wizard.reason = "Customer changed their mind"
        wizard.action_cancel_and_refund()
        body = order.message_ids[0].body

        self.assertIn("Customer changed their mind", body)
        self.assertIn("Shop Floor", body)
        self.assertIn(self.env.user.display_name, body)

    # --- who may do it -------------------------------------------------------

    def test_only_a_sales_manager_may_do_this(self):
        """It gives money back and unwinds a day's work on the floor."""
        order = self._order()
        self._paid(order)
        clerk = self.env["res.users"].create({
            "name": "A clerk", "login": "aa_clerk",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("sales_team.group_sale_salesman").id])],
        })
        wizard = self._wizard(order).with_user(clerk)

        with self.assertRaises(AccessError):
            wizard.action_cancel_and_refund()

        self.assertNotEqual(order.state, "cancel")

    def test_cancelling_a_cancelled_order_says_so(self):
        order = self._order()
        order._action_cancel()

        with self.assertRaises(UserError):
            self._wizard(order).action_cancel_and_refund()
