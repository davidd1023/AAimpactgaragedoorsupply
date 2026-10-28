"""ONE CANCELLATION EMAIL PER ORDER, WHOEVER CANCELS IT.

Owner, 2026-10-27: the customer should be told when their order is cancelled
in Manufacturing - *"i dont want to send multiple emails if i also have to
cancel it again in the sales module or some other module that isn't
manufacturing."*

So the tests that matter are the ones that cancel the same order TWICE, by
different routes, and count. And the one that cancels a single job out of
three and insists nothing is sent, because an order is not one job: asked, the
owner chose the email to go when nothing is left being made.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class CancellationEmailCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.company.write({
            "street": "9753 NW 91st Ct", "city": "Medley", "zip": "33178",
            "phone": "+1 786-238-7640", "email": "office@aaigd.com",
        })
        self.customer = self.env["res.partner"].create({
            "name": "Hector the Fitter", "email": "hector@example.com"})
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 100.0})
        self.order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 2})],
        })
        self.order.action_confirm()

    # --- helpers -----------------------------------------------------------

    def _emails(self):
        return self.env["mail.message"].search([
            ("model", "=", "sale.order"),
            ("res_id", "=", self.order.id),
            ("subject", "ilike", "cancelled"),
        ])

    def _job(self):
        """A manufacturing order raised for this sale order.

        Linked by `origin`, which is the link every job has - the station
        jobs also carry aa_sale_line_id, but a prepared track job does not.
        """
        return self.env["mrp.production"].create({
            "product_id": self.product.id,
            "product_qty": 1.0,
            "origin": self.order.name,
        })

    # --- cancelling in manufacturing ---------------------------------------

    def test_cancelling_the_only_job_tells_the_customer(self):
        job = self._job()

        job.action_cancel()

        self.assertEqual(len(self._emails()), 1,
                         "nothing was sent when the work was called off")

    def test_cancelling_one_job_of_three_tells_nobody(self):
        """An order is not one job. Owner, 2026-10-27, asked whether the email
        should go on the first job or the last: the last. Cancelling the
        springs while the hardware kit is still being packed is a change to
        one part of the order, not a cancellation of it."""
        springs, kit, cables = self._job(), self._job(), self._job()

        springs.action_cancel()

        self.assertFalse(self._emails(),
                         "the customer was told their order was off while two"
                         " jobs were still being made for them")
        self.assertEqual(kit.state + cables.state, "draftdraft")

    def test_cancelling_the_last_job_tells_the_customer_once(self):
        springs, kit, cables = self._job(), self._job(), self._job()

        springs.action_cancel()
        kit.action_cancel()
        cables.action_cancel()

        self.assertEqual(len(self._emails()), 1,
                         "three cancelled jobs should be one email, not three")

    def test_a_job_that_was_finished_is_not_nothing(self):
        """Something was built. "Your order is cancelled" is the wrong thing
        to say about an order that was half made, so this path stays quiet and
        leaves it to a Sales cancellation."""
        done_job, other = self._job(), self._job()
        done_job.write({"state": "done"})

        other.action_cancel()

        self.assertFalse(self._emails())

    # --- and not twice -----------------------------------------------------

    def test_cancelling_in_sales_after_manufacturing_sends_nothing_more(self):
        """THE ONE HE ASKED FOR. The jobs come off the floor, then the order
        is cancelled in Sales - which is the same news a second time."""
        self._job().action_cancel()
        self.assertEqual(len(self._emails()), 1)

        self.order._action_cancel()

        self.assertEqual(len(self._emails()), 1,
                         "cancelling it again in Sales sent a second email")

    def test_cancelling_in_sales_first_also_only_sends_one(self):
        """The same two steps the other way round. Cancelling the order takes
        its jobs off the floor by itself, which is a second route into the
        same email."""
        self.order._action_cancel()

        self.assertEqual(len(self._emails()), 1)

    def test_the_stamp_is_what_stops_it(self):
        self.order._action_cancel()
        stamped = self.order.aa_cancel_email_sent

        self.assertTrue(stamped, "nothing recorded that the customer knows")

        self.order._aa_send_cancellation_email()

        self.assertEqual(self.order.aa_cancel_email_sent, stamped)
        self.assertEqual(len(self._emails()), 1)

    # --- and not for things that are not orders ----------------------------

    def test_a_quotation_nobody_confirmed_tells_nobody(self):
        """Telling somebody their order is off when they never placed one is
        worse than silence."""
        quotation = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 1})],
        })

        quotation._action_cancel()

        self.assertFalse(self.env["mail.message"].search([
            ("model", "=", "sale.order"), ("res_id", "=", quotation.id),
            ("subject", "ilike", "cancelled"),
        ]))

    def test_a_customer_with_no_email_address_is_not_a_failure(self):
        self.customer.email = False

        self.order._action_cancel()

        self.assertEqual(self.order.state, "cancel",
                         "the cancellation itself must still go through")
        self.assertFalse(self.order.aa_cancel_email_sent)

    # --- the wizard still works, and still says what it refunded -----------

    def test_the_wizard_sends_exactly_one_and_waits_for_the_refund(self):
        """It cancels the shop floor jobs first and refunds after, so the
        email must not go out at step one - it would promise a refund that
        had not been attempted yet."""
        self._job()
        wizard = self.env["aa.order.cancel"].create({"order_id": self.order.id})
        self.env.user.group_ids = [
            (4, self.env.ref("sales_team.group_sale_manager").id)]

        wizard.action_cancel_and_refund()

        self.assertEqual(len(self._emails()), 1,
                         "the wizard sent none, or sent one per step")
