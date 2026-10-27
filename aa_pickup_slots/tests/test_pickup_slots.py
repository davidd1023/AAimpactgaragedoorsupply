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

from datetime import date

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
        self.order.aa_pickup_slot = "10"

        self.assertFalse(self.order._aa_pickup_problem())

    def test_a_day_that_is_too_soon_is_refused(self):
        """The page can sit open for a day, and anybody can post this route a
        date of their own choosing."""
        self.order.carrier_id = self.pickup
        self.order.aa_pickup_date = date.today()
        self.order.aa_pickup_slot = "10"

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
        self.order.aa_pickup_slot = "12"

        try:
            self.order._check_cart_is_ready_to_be_paid()
        except ValidationError as refused:
            self.assertNotIn("choose the day", str(refused),
                             "it still wants a slot after one was given")

    # --- where it has to appear -------------------------------------------

    def test_the_label_reads_as_one_line(self):
        self.order.aa_pickup_date = date(2026, 10, 29)
        self.order.aa_pickup_slot = "14"

        self.assertEqual(self.order.aa_pickup_label,
                         "Thu 29 Oct, 2:00 PM - 4:30 PM")

    def test_an_order_with_no_slot_has_no_label(self):
        self.assertFalse(self.order.aa_pickup_label)

    def test_the_slot_reaches_the_transfer(self):
        """"the chosen slot appears on the order and the Dispatch list" - and
        the Dispatch list is a list of transfers."""
        self.order.carrier_id = self.pickup
        self.order.aa_pickup_date = self.order._aa_earliest_pickup()
        self.order.aa_pickup_slot = "08"
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
        self.assertIn("aa_pickup_day", arch)
        self.assertIn("aa_pickup_window", arch)
