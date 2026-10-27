"""THE PICKUP SLOT: WHEN IT MAY BE, AND WHERE IT HAS TO SHOW UP.

Owner, 2026-10-27, with three answers that this holds to:

  * an order placed MONDAY is collectable from THURSDAY - the lead time is
    two WHOLE working days and the day it was placed is not one of them;
  * two-hour windows;
  * pickup orders only, and required, so nothing reaches Dispatch blank.

The arithmetic is the part worth testing hardest. Everything else is a field
appearing in a list; getting Friday wrong means a customer driving over on a
day their order is not made yet.
"""

import json
from datetime import date

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.exceptions import ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class PickupSlotCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.customer = self.env["res.partner"].create({
            "name": "Hector the Fitter", "email": "hector@example.com",
            "street": "2550 W 60th Pl", "city": "Hialeah", "zip": "33016",
            "country_id": self.env.ref("base.us").id,
            "state_id": self.env.ref("base.state_us_14").id})
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 100.0})
        # PUBLISHED, so Odoo's own availability check passes and the gate
        # test reaches ours. Without this _check_cart_is_ready_to_be_paid
        # refuses with "the delivery method is not compatible" and an
        # assertRaises here would pass while proving nothing.
        self.pickup = self.env["delivery.carrier"].create({
            "name": "Pickup - Medley Warehouse",
            "aa_is_pickup": True,
            "website_published": True,
            "product_id": self.env["product.product"].create({
                "name": "Pickup", "type": "service", "list_price": 0.0}).id,
        })
        self.courier = self.env["delivery.carrier"].create({
            "name": "Local Delivery",
            "website_published": True,
            "product_id": self.env["product.product"].create({
                "name": "Delivery", "type": "service", "list_price": 15.0}).id,
        })
        self.order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 2})],
        })

    # --- two whole working days, and the order day is not one -------------

    def test_an_order_placed_monday_is_ready_thursday(self):
        """HIS ANSWER, asked directly: Tuesday and Wednesday are the two
        labour days, Thursday is the first day it can be handed over."""
        monday = date(2026, 10, 26)

        self.assertEqual(self.order._aa_earliest_pickup(monday),
                         date(2026, 10, 29))

    def test_an_order_placed_friday_is_ready_wednesday(self):
        """The weekend is not two labour days. The clock starts Monday."""
        friday = date(2026, 10, 30)

        self.assertEqual(self.order._aa_earliest_pickup(friday),
                         date(2026, 11, 4))

    def test_an_order_placed_saturday_is_also_ready_wednesday(self):
        """Nothing is made at the weekend, so a Saturday order is no further
        on than the Friday one before it."""
        saturday = date(2026, 10, 31)

        self.assertEqual(self.order._aa_earliest_pickup(saturday),
                         date(2026, 11, 4))

    def test_a_holiday_is_not_a_labour_day(self):
        """Owner's closed days: neither counted towards the two days nor
        offered to collect on. Christmas 2026 is a Friday."""
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.closed_days", "2026-12-24, 2026-12-25")
        tuesday = date(2026, 12, 22)

        # Wed 23 is one labour day; Thu 24 and Fri 25 are closed; Mon 28 is
        # the second; so the earliest collection is Tuesday 29.
        self.assertEqual(self.order._aa_earliest_pickup(tuesday),
                         date(2026, 12, 29))

    def test_a_closed_day_is_never_offered(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.closed_days", "2026-12-25")
        offered = [day for day, _label in self.order._aa_pickup_choices()]

        self.assertNotIn(date(2026, 12, 25), offered)

    def test_nothing_at_a_weekend_is_ever_offered(self):
        for day, _label in self.order._aa_pickup_choices():
            self.assertLess(day.weekday(), 5,
                            "%s is a weekend and nobody is here" % day)

    def test_a_mistyped_closed_day_does_not_take_the_shop_down(self):
        """A checkout that 500s because somebody fat-fingered a date is a
        worse fault than a day staying open."""
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.closed_days", "the 25th of December, 2026-12-25")

        self.assertIn(date(2026, 12, 25), self.order._aa_closed_days())

    # --- who is asked ------------------------------------------------------

    def test_a_delivery_order_is_never_asked(self):
        """Asked who should have to choose, he said pickup orders only."""
        self.order.carrier_id = self.courier

        self.assertFalse(self.order._aa_is_pickup())
        self.assertFalse(self.order._aa_pickup_problem())

    def test_a_pickup_order_with_no_slot_cannot_be_paid(self):
        self.order.carrier_id = self.pickup

        self.assertTrue(self.order._aa_is_pickup())
        self.assertIn("choose the day", self.order._aa_pickup_problem())

    def test_a_pickup_order_with_a_slot_is_happy(self):
        self.order.carrier_id = self.pickup
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_time = 10.0

        self.assertFalse(self.order._aa_pickup_problem())

    def test_a_day_that_is_too_soon_is_refused(self):
        """The page can sit open for a day, and anybody can post this route a
        date of their own choosing."""
        self.order.carrier_id = self.pickup
        self.order.aa_pickup_date = date.today()
        self.order.aa_pickup_time = 10.0

        self.assertIn("no longer available", self.order._aa_pickup_problem())

    def test_the_payment_gate_actually_refuses(self):
        """_aa_pickup_problem only says so; this is the thing that stops a
        pickup order being paid for without a slot.

        THE MESSAGE IS ASSERTED, not just the exception. Odoo's own checks
        run first and raise the same class for a cart with no delivery
        method, so a bare assertRaises here would pass whether or not any of
        this works."""
        self.order.carrier_id = self.pickup

        with self.assertRaises(ValidationError) as caught:
            self.order._check_cart_is_ready_to_be_paid()

        self.assertIn("choose the day", str(caught.exception),
                      "something else refused, so this proves nothing")

    def test_the_payment_gate_lets_a_booked_order_through(self):
        """The other half: with a slot, our check is silent and whatever
        Odoo makes of the cart is its own business."""
        self.order.carrier_id = self.pickup
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_time = 12.5

        try:
            self.order._check_cart_is_ready_to_be_paid()
        except ValidationError as refused:
            self.assertNotIn("choose the day", str(refused),
                             "it still wants a slot after one was given")

    # --- where it has to appear -------------------------------------------

    def test_the_label_reads_as_one_line(self):
        self.order.aa_pickup_date = date(2026, 10, 29)
        self.order.aa_pickup_time = 14.0

        self.assertEqual(self.order.aa_pickup_label,
                         "Thu 29 Oct, 2:00 PM")

    def test_an_order_with_no_slot_has_no_label(self):
        self.assertFalse(self.order.aa_pickup_label)

    def test_the_slot_reaches_the_transfer(self):
        """"the chosen slot appears on the order and the Dispatch list" - and
        the Dispatch list is a list of transfers."""
        self.order.carrier_id = self.pickup
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_time = 7.5
        self.order.action_confirm()

        pickings = self.order.picking_ids

        self.assertTrue(pickings, "the order made no transfer to carry it")
        for picking in pickings:
            self.assertEqual(picking.aa_pickup_date, self.order.aa_pickup_date)
            self.assertEqual(picking.aa_pickup_label,
                             self.order.aa_pickup_label)

    def test_a_delivered_order_leaves_the_transfer_blank(self):
        self.order.carrier_id = self.courier
        self.order.action_confirm()

        for picking in self.order.picking_ids:
            self.assertFalse(picking.aa_pickup_label)


@tagged("post_install", "-at_install")
class PickupSlotPageCase(HttpCase):
    """The checkout page has to render with the block in it."""

    def test_the_checkout_page_still_renders(self):
        """A mistake in the QWeb shows up nowhere until somebody tries to
        buy something."""
        page = self.url_open("/shop")

        self.assertEqual(page.status_code, 200)

    def test_the_block_is_in_the_checkout_view(self):
        """The xpath found its anchor, so the question is on the page where
        the delivery methods are - and it is rendered always and hidden,
        because Odoo swaps delivery methods without reloading."""
        arch = self.env.ref("website_sale.checkout").get_combined_arch()

        self.assertIn("aa_pickup_slot", arch)
        self.assertIn("aa_pickup_day_button", arch)
        self.assertIn("aa_pickup_calendar", arch)
        self.assertIn("aa_pickup_times", arch)


@tagged("post_install", "-at_install")
class PickupGateCase(TransactionCase):
    """THE GATE THAT ACTUALLY STOPS THEM.

    Owner, 2026-10-27: "currently they dont need to do either to proceed."
    He was right. `_check_cart_is_ready_to_be_paid` is only reached on the
    zero-total path in Odoo 19, so a pickup order with something to pay
    walked straight past it. `_get_shop_payment_errors` is the one the
    payment page consults and the one /shop/payment/validate raises on.
    """

    def setUp(self):
        super().setUp()
        from odoo.addons.aa_pickup_slots.controllers.main import (
            AAWebsiteSalePickup,
        )
        self.controller = AAWebsiteSalePickup()
        self.customer = self.env["res.partner"].create({
            "name": "Hector", "email": "hector@example.com",
            "street": "2550 W 60th Pl", "city": "Hialeah", "zip": "33016",
            "country_id": self.env.ref("base.us").id})
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 100.0})
        self.pickup = self.env["delivery.carrier"].create({
            "name": "Pickup - Medley Warehouse", "aa_is_pickup": True,
            "website_published": True,
            "product_id": self.env["product.product"].create({
                "name": "Pickup", "type": "service"}).id})
        self.order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "carrier_id": self.pickup.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 1})]})

    def _titles(self):
        """The errors the payment page would show.

        Inside a MockRequest because the base implementation reaches for
        `request.website` - `website_published` is a computed field whose
        search needs one. Calling the controller bare raised
        "'NoneType' object has no attribute 'uid'" and, worse, returned an
        EMPTY list, which would have made a test pass by finding nothing.
        """
        website = self.env["website"].search([], limit=1)

        with MockRequest(self.env, website=website):
            errors = self.controller._get_shop_payment_errors(self.order)

        return [title for title, _msg in errors]

    def test_a_pickup_with_no_slot_is_an_error_on_the_payment_page(self):
        self.assertIn("Pickup time needed", self._titles())

    def test_a_booked_pickup_is_not(self):
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_time = 10.0

        self.assertNotIn("Pickup time needed", self._titles())

    def test_odoo_s_own_errors_still_come_through(self):
        """super() is called, so nothing Odoo would have said is lost.

        EVERY carrier is unpublished, not just ours: the database has others
        and leaving them published meant Odoo found a shipping method, said
        nothing, and this passed or failed for reasons of its own."""
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_time = 10.0
        self.env["delivery.carrier"].search([]).write(
            {"website_published": False})

        self.assertTrue(self._titles(),
                        "Odoo's own shipping error went missing")

    def test_the_calendar_is_given_the_same_days_the_server_allows(self):
        """The squares that can be clicked and the days that are accepted are
        one list, so they cannot drift apart."""
        import json

        offered = json.loads(self.order._aa_pickup_days_json())
        allowed = [day.isoformat()
                   for day, _label in self.order._aa_pickup_choices()]

        self.assertEqual(offered, allowed)
        self.assertTrue(offered, "the calendar would have nothing to show")


@tagged("post_install", "-at_install")
class PickupTimesCase(TransactionCase):
    """THE TIMES ON OFFER, after he widened them.

    Owner, 2026-10-27: "the customer should be able to choose anytime between
    7 and 4, but dont make it a dropdown ... let them choose a larger range of
    time." So the four two-hour windows became half hours across the open day.
    """

    def setUp(self):
        super().setUp()
        self.order = self.env["sale.order"].create({
            "partner_id": self.env["res.partner"].create({"name": "H"}).id})

    def _times(self):
        return [value for value, _label in self.order._aa_pickup_time_choices()]

    def test_the_day_runs_from_seven_to_four(self):
        times = self._times()

        self.assertEqual(times[0], 7.0)
        self.assertEqual(times[-1], 16.0)

    def test_they_come_in_half_hours(self):
        times = self._times()

        self.assertEqual(len(times), 19, times)
        self.assertIn(7.5, times)
        self.assertIn(12.5, times)

    def test_the_hours_can_be_moved_without_a_deploy(self):
        """He has already changed them once."""
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.open_from", "9.0")
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.open_to", "11.0")

        self.assertEqual(self._times(), [9.0, 9.5, 10.0, 10.5, 11.0])

    def test_hours_typed_backwards_fall_back_rather_than_offer_nothing(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.open_from", "16.0")
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_pickup_slots.open_to", "7.0")

        self.assertEqual(self._times()[0], 7.0)
        self.assertEqual(self._times()[-1], 16.0)

    def test_the_labels_read_as_a_person_would_say_them(self):
        labels = dict(self.order._aa_pickup_time_choices())

        self.assertEqual(labels[7.0], "7:00 AM")
        self.assertEqual(labels[7.5], "7:30 AM")
        self.assertEqual(labels[12.0], "12:00 PM")
        self.assertEqual(labels[12.5], "12:30 PM")
        self.assertEqual(labels[16.0], "4:00 PM")

    def test_a_time_we_are_shut_is_refused(self):
        pickup = self.env["delivery.carrier"].create({
            "name": "Pickup", "aa_is_pickup": True,
            "product_id": self.env["product.product"].create(
                {"name": "P", "type": "service"}).id})
        self.order.carrier_id = pickup
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_time = 22.0

        self.assertIn("not open at that time", self.order._aa_pickup_problem())


@tagged("post_install", "-at_install")
class PickupRouteCase(HttpCase):
    """THE ROUTE THE PAGE ACTUALLY CALLS.

    Everything else tests models. This calls /shop/pickup_slot over HTTP,
    because the first version of it used `website.sale_get_order()` - gone in
    Odoo 19 - and blew up with AttributeError the moment a customer picked a
    date on the live site. Twenty-nine passing tests never touched it.

    A handled answer comes back as a RESULT. A crash comes back with a
    top-level "error", which is the thing being watched for here.
    """

    def _call(self, **params):
        response = self.url_open(
            "/shop/pickup_slot",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": params}),
            headers={"Content-Type": "application/json"})

        self.assertEqual(response.status_code, 200)

        return response.json()

    def test_the_route_answers_instead_of_exploding(self):
        payload = self._call(date="", time=0)

        self.assertNotIn("error", payload,
                         "the route raised: %s" % payload.get("error"))
        self.assertIn("result", payload)

    def test_with_no_cart_it_says_so_politely(self):
        payload = self._call(date="2026-12-01", time=10.0)

        self.assertNotIn("error", payload)
        self.assertEqual(payload["result"].get("error"), "no-cart")

    def test_a_nonsense_time_does_not_raise(self):
        """float("half past ten") must not reach the customer as a 500."""
        payload = self._call(date="", time="half past ten")

        self.assertNotIn("error", payload)
