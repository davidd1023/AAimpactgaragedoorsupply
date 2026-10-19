"""TELLING THE CUSTOMER THEIR ORDER IS READY.

The owner, 2026-10-19: from the dispatch page, send the customer a message
saying "Your order ___ is ready for pickup at Medley" - no more detail than
that - and let the shop choose in Settings which of its addresses it comes
from.

Three decisions he made when asked: a BUTTON rather than an automatic send
(an email cannot be unsent and the last box gets ticked by mistake), the
CUSTOMER'S OWN order number rather than the W/O number off the printed sheet
(they have never seen ours), and email only for now.
"""

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class OrderReadyAlertCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.customer = self.env["res.partner"].create({
            "name": "Hector the Fitter",
            "email": "hector@example.com",
        })
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 10.0})
        self.env.company.write({"city": "Medley", "phone": "+1 786-238-7640",
                                "email": "office@aaigd.com"})

    def _order(self):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 1})],
        })
        order.action_confirm()

        return order

    def _picking(self):
        """The order's OUTGOING transfer - the one that leaves the building.

        NOT picking_ids[:1], which is what I wrote first and which was wrong
        twice over. This warehouse delivers in TWO STEPS (pick_ship): confirming
        the order makes only the internal PICK that gathers goods to Output,
        and the delivery the customer collects does not exist until that pick
        is finished - at which point it appears already Ready, because its goods
        are standing in Output reserved for it.

        That is the real sequence and it is the whole point of the feature: the
        moment somebody finishes picking an order is the moment it is ready to
        be collected. So the fixture does the pick, as the warehouse does.

        My first tests took picking_ids[:1] and passed anyway, because nothing
        in the action cares what type a transfer is - they were quietly
        exercising an internal move instead of the delivery the button appears
        on.
        """
        order = self._order()
        pick = order.picking_ids.filtered(
            lambda p: p.picking_type_id.code != "outgoing")

        for step in pick:
            self.env["stock.quant"]._update_available_quantity(
                self.product, step.location_id, 10.0)
            step.action_assign()

            for move in step.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True

            step.button_validate()

        order.invalidate_recordset()
        picking = order.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing")[:1]
        self.assertTrue(picking, "picking the order made no delivery")

        return order, picking

    def _sent(self, picking):
        """The message the customer was sent, as a mail.mail record."""
        return self.env["mail.mail"].search(
            [("model", "=", "stock.picking"), ("res_id", "=", picking.id)],
            order="id desc", limit=1)

    # --- what the customer is told -------------------------------------------

    def test_the_message_says_the_order_is_ready(self):
        order, picking = self._picking()
        picking.action_notify_ready()
        mail = self._sent(picking)

        self.assertTrue(mail, "nothing was sent")
        self.assertIn(order.name, mail.subject)
        self.assertIn("is ready", mail.subject)
        body = mail.body_html or ""
        self.assertIn(order.name, body)
        self.assertIn("ready for pickup", body)
        self.assertIn("Medley", body)

    def test_it_is_the_customer_s_own_number_not_ours(self):
        """THE NUMBER THEY ALREADY HAVE. The W/O number is on our paperwork
        and they have never seen it."""
        order, picking = self._picking()
        picking.action_notify_ready()
        body = self._sent(picking).body_html or ""

        self.assertIn(order.name, body)
        self.assertNotIn(picking.name, body,
                         "the W/O number means nothing to a customer")

    def test_it_goes_to_the_customer(self):
        """ADDRESSED TO THE CONTACT, not to a typed-in address: the template
        names the partner, so Odoo keeps the recipient as a contact and the
        address follows whatever is on the contact today."""
        _order, picking = self._picking()
        picking.action_notify_ready()
        mail = self._sent(picking)

        self.assertIn(self.customer, mail.recipient_ids)
        self.assertEqual(self.customer.email, "hector@example.com")

    def test_it_says_nothing_about_what_is_in_the_box(self):
        """"we dont need to give them too much detail just that their order
        is ready" - so no list of parts and no prices."""
        _order, picking = self._picking()
        picking.action_notify_ready()
        body = self._sent(picking).body_html or ""

        self.assertNotIn("A thing", body)
        self.assertNotIn("10.0", body)

    def test_the_town_comes_from_the_warehouse(self):
        """An order picked at a second site must not send somebody to the
        first one."""
        _order, picking = self._picking()
        picking.picking_type_id.warehouse_id.partner_id.city = "Hialeah"
        self.assertEqual(picking._dispatch_pickup_place(), "Hialeah")

    def test_no_town_is_better_than_half_a_sentence(self):
        """"ready for pickup" is true; "ready for pickup at" is not a
        sentence."""
        _order, picking = self._picking()
        picking.picking_type_id.warehouse_id.partner_id.city = False
        self.env.company.city = False
        self.assertEqual(picking._dispatch_pickup_place(), "")
        picking.action_notify_ready()
        body = self._sent(picking).body_html or ""
        self.assertIn("ready for pickup", body)
        self.assertNotIn("pickup at", body)

    # --- who it comes from ---------------------------------------------------

    def test_the_sender_is_the_one_set_in_settings(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "work_order_sheet.ready_email_from", "sales@aaigd.com")
        _order, picking = self._picking()
        picking.action_notify_ready()
        mail = self._sent(picking)

        self.assertIn("sales@aaigd.com", mail.email_from or "")
        self.assertIn("sales@aaigd.com", mail.reply_to or "",
                      "a reply has to come back to a mailbox somebody reads")

    def test_with_nothing_set_it_comes_from_the_company(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "work_order_sheet.ready_email_from", "")
        _order, picking = self._picking()
        self.assertEqual(picking._dispatch_ready_email_from(), "office@aaigd.com")

    def test_an_address_that_is_not_one_is_refused_when_it_is_saved(self):
        """NOT WHEN THE FIRST CUSTOMER IS EMAILED. A typo here does not fail
        loudly - the mail goes out from somewhere else, or bounces into a
        mailbox nobody reads, and the shop finds out when a customer who was
        never told rings up."""
        settings = self.env["res.config.settings"].create({})

        for typed in ("no", "no@no", "two@a.com, three@b.com", "a b@c.com"):
            with self.assertRaises(ValidationError, msg=typed):
                settings.write({"dispatch_ready_email_from": typed})

    def test_a_name_in_front_of_the_address_is_allowed(self):
        """What somebody types when they want the shop's name on it."""
        settings = self.env["res.config.settings"].create({})
        settings.write({"dispatch_ready_email_from": "AA Impact <sales@aaigd.com>"})
        self.assertTrue(settings.dispatch_ready_email_from)

    # --- pressing it, and pressing it twice ----------------------------------

    def test_the_page_remembers_that_it_was_sent(self):
        _order, picking = self._picking()
        self.assertFalse(picking.dispatch_ready_sent_on)
        picking.action_notify_ready()

        self.assertTrue(picking.dispatch_ready_sent_on)
        self.assertEqual(picking.dispatch_ready_sent_to, "hector@example.com")

    def test_it_can_be_sent_again_on_purpose(self):
        """The words on the button change rather than the button going away:
        a second message should be a thing somebody means to send."""
        _order, picking = self._picking()
        picking.action_notify_ready()
        first = self._sent(picking)
        picking.action_notify_ready()
        second = self._sent(picking)

        self.assertNotEqual(first, second, "the second press sent nothing")

    def test_a_customer_with_no_address_is_said_out_loud(self):
        """SAID PLAINLY RATHER THAN FAILING QUIETLY, while somebody is still
        looking at the order."""
        _order, picking = self._picking()
        self.customer.email = False

        with self.assertRaises(UserError):
            picking.action_notify_ready()

        self.assertFalse(picking.dispatch_ready_sent_on,
                         "it must not claim to have told anybody")

    def test_the_order_s_log_keeps_a_record(self):
        """So the next person to open it can see it was done, and when."""
        _order, picking = self._picking()
        picking.action_notify_ready()
        messages = picking.message_ids.filtered(
            lambda m: "is ready" in (m.body or ""))
        self.assertTrue(messages, "nothing in the order's log")
        self.assertIn("hector@example.com", messages[0].body)


@tagged("post_install", "-at_install")
class SentWithoutBeingAskedCase(OrderReadyAlertCase):
    """"send the email to the customer automatically, well keep the button for
    resending in case we ever need it" (owner, 2026-10-19).

    READY MEANS READY: a delivery is Ready when everything on it is reserved
    and could be handed over, which for a made-to-order door is when the shop
    has finished making it - the springs and tracks only reach stock when their
    manufacturing orders are marked done. These tests put the stock there and
    let the sweep find it.
    """

    def setUp(self):
        super().setUp()
        # THE STAMP IS LEFT WHERE IT IS, and my first draft of this moved it
        # back to the year 2000 "so the test orders are included" - which also
        # included this database's own 23 ready-and-never-told deliveries and
        # sent the lot. That is the exact hazard the stamp exists to prevent,
        # found by a test that had disabled it. Orders made in the test are
        # made now, which is after it, so nothing needs moving.
        self.env["ir.config_parameter"].sudo().set_param(
            "work_order_sheet.ready_email_auto", "True")

    def _ready_picking(self):
        """A delivery standing ready: picked, in Output, waiting to be
        collected. Which is what _picking already leaves behind here."""
        _order, picking = self._picking()
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "assigned", "the delivery is not ready")

        return picking

    def _sweep(self):
        return self.env["stock.picking"]._cron_notify_ready()

    # --- it goes by itself ---------------------------------------------------

    def test_a_ready_delivery_tells_the_customer_by_itself(self):
        picking = self._ready_picking()
        self._sweep()

        self.assertTrue(picking.dispatch_ready_sent_on)
        self.assertTrue(self._sent(picking), "nothing was actually sent")

    def test_a_delivery_that_is_not_ready_is_left_alone(self):
        """Nothing is reserved, so nothing is ready, so nobody is told."""
        _order, picking = self._picking()
        picking.do_unreserve()
        picking.invalidate_recordset()
        self.assertNotEqual(picking.state, "assigned")
        self._sweep()
        self.assertFalse(picking.dispatch_ready_sent_on)

    def test_nobody_is_told_twice(self):
        """THE STAMP IS THE GUARD, which is what makes a sweep safe to run
        every quarter of an hour for ever."""
        picking = self._ready_picking()
        self._sweep()
        self._sweep()
        self.assertEqual(
            len(self.env["mail.mail"].search(
                [("model", "=", "stock.picking"), ("res_id", "=", picking.id)])),
            1)

    def test_the_button_still_sends_it_again_afterwards(self):
        """The owner kept the button on purpose."""
        picking = self._ready_picking()
        self._sweep()
        picking.action_notify_ready()
        self.assertEqual(
            len(self.env["mail.mail"].search(
                [("model", "=", "stock.picking"), ("res_id", "=", picking.id)])),
            2)

    # --- and the guards around it --------------------------------------------

    def test_switching_it_off_stops_it(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "work_order_sheet.ready_email_auto", "False")
        picking = self._ready_picking()

        self._sweep()
        self.assertFalse(picking.dispatch_ready_sent_on)

    def test_the_back_catalogue_is_not_emailed(self):
        """SWITCHING THIS ON MUST NOT TELL FIFTY PEOPLE AT ONCE that an order
        they collected weeks ago is ready. Only orders raised since the day it
        was switched on go by themselves; an older one can still be told with
        the button."""
        picking = self._ready_picking()
        self.env["ir.config_parameter"].sudo().set_param(
            "work_order_sheet.ready_auto_since", "2099-01-01 00:00:00")

        self._sweep()
        self.assertFalse(picking.dispatch_ready_sent_on)

        # And the button is still there for it.
        picking.action_notify_ready()
        self.assertTrue(picking.dispatch_ready_sent_on)

    def test_a_customer_with_no_address_is_skipped_not_claimed(self):
        """The sweep cannot say it out loud - there is nobody to say it to -
        so it leaves the order untouched for the button to complain about."""
        picking = self._ready_picking()
        self.customer.email = False

        self._sweep()
        self.assertFalse(picking.dispatch_ready_sent_on,
                         "it must not claim to have told anybody")

    def test_one_bad_order_does_not_stop_the_rest(self):
        """A dead mail server or a template that cannot render for one order
        is no reason for the next twenty customers to hear nothing."""
        first = self._ready_picking()
        second = self._ready_picking()
        real = type(self.env["stock.picking"]).action_notify_ready

        def explode(picking):
            if picking.id == first.id:
                raise ValueError("the mail server fell over")

            return real(picking)

        patched = type(self.env["stock.picking"])
        patched.action_notify_ready = explode

        try:
            self._sweep()
        finally:
            patched.action_notify_ready = real

        self.assertFalse(first.dispatch_ready_sent_on)
        self.assertTrue(second.dispatch_ready_sent_on)
