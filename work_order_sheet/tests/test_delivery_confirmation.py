import base64
import re

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, tagged

from .test_work_order_sheet import visible_text

# The smallest valid PNG, which is what the pad posts a bigger version of.
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKm"
       "MIQAAAABJRU5ErkJggg==")
SIGNATURE = "data:image/png;base64," + PNG


@tagged("post_install", "-at_install")
class TestDeliveryConfirmation(HttpCase):
    """The customer's receipt: what they were handed, and their name on it.

    A delivery note that signs itself back. What comes back today is a piece
    of paper nobody can find, or nothing at all.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "A Customer"})
        self.hinge = self.env["product.product"].create({
            "name": "No 2 Hinge Galvanized", "type": "consu",
            "is_storable": True, "list_price": 10.0})
        self.track = self.env["product.product"].create({
            "name": '2" Vertical Track 76" - 7\' Door Height Black',
            "type": "consu", "is_storable": True, "list_price": 42.0})
        self.cable = self.env["product.product"].create({
            "name": '1/8" 7X19 GAC Lift Cable 110" Black',
            "type": "consu", "is_storable": True, "list_price": 12.0})
        # A spring is recognised from its order line where there is one, and
        # from where the shop filed it otherwise - which is how the live
        # catalogue is set up.
        self.spring = self.env["product.product"].create({
            "name": "Custom Torsion Spring Assembly",
            "type": "consu", "is_storable": True, "list_price": 300.0,
            "categ_id": self.env["product.category"].create(
                {"name": "Springs"}).id})

    def _delivery(self, products=None):
        """The transfer that leaves the building.

        BUILT DIRECTLY, not through a sale order. This warehouse delivers in
        two steps - a pick, then the delivery - so confirming an order does
        not produce the outgoing transfer until the pick is done, and what is
        being tested here is the delivery, not the route that makes one.
        """
        products = products or ((self.hinge, 4), (self.track, 2))
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "outgoing")], limit=1)
        self.assertTrue(picking_type, "this database delivers nothing")
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner.id,
            "origin": "S00123",
            "location_id": picking_type.default_location_src_id.id
                           or self.env.ref("stock.stock_location_stock").id,
            "location_dest_id": picking_type.default_location_dest_id.id
                                or self.env.ref("stock.stock_location_customers").id,
            "move_ids": [
                (0, 0, {"product_id": product.id, "product_uom_qty": qty,
                        "location_id": picking_type.default_location_src_id.id
                                       or self.env.ref("stock.stock_location_stock").id,
                        "location_dest_id": picking_type.default_location_dest_id.id
                                            or self.env.ref("stock.stock_location_customers").id})
                for product, qty in products
            ],
        })
        picking.action_confirm()

        return picking

    def _page(self, picking, token=None):
        response = self.url_open(
            "/delivery/%s" % (token or picking.dispatch_access_token))
        self.assertEqual(response.status_code, 200)

        return response

    def _sign(self, picking, name="Jane Customer", signature=SIGNATURE,
              items=None):
        """Tick rows the way the page does: one box per thing handed over."""
        rows = picking._dispatch_items() if items is None else items
        data = {"signed_by": name, "signature": signature}

        for row in rows:
            key = row["key"] if isinstance(row, dict) else row.id
            data["item_%s" % key] = "1"

        return self.url_open(
            "/delivery/%s/sign" % picking.dispatch_access_token, data=data)

    # --- the form exists without anybody making it ---------------------------

    def test_a_delivery_gets_its_form_when_it_is_confirmed(self):
        """The link has to be ON the order when somebody looks for it - one
        made only by pressing a button is one the driver cannot find."""
        picking = self._delivery()
        self.assertTrue(picking.dispatch_access_token)
        self.assertTrue(picking.dispatch_form_date)
        self.assertEqual(picking.dispatch_state, "open")
        self.assertIn("/delivery/", picking.dispatch_url)

    def test_an_internal_transfer_gets_none(self):
        """Nobody signs for a move between two of our own shelves."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.env["stock.picking.type"].search(
                [("code", "=", "internal")], limit=1).id,
            "location_id": self.env.ref("stock.stock_location_stock").id,
            "location_dest_id": self.env.ref("stock.stock_location_output").id,
        })
        picking.action_confirm()
        self.assertFalse(picking.dispatch_access_token)
        self.assertFalse(picking.dispatch_state)

    def test_a_wrong_link_shows_nothing(self):
        self._delivery()
        self.assertEqual(self.url_open("/delivery/nope").status_code, 404)
        self.assertEqual(
            self.url_open("/delivery/%s" % ("f" * 64)).status_code, 404)

    # --- what the customer sees ----------------------------------------------

    def test_the_form_lists_everything_being_delivered(self):
        picking = self._delivery()
        text = visible_text(self._page(picking).text)

        self.assertIn("No 2 Hinge Galvanized", text)
        self.assertIn("Vertical Track", text)
        self.assertIn("Tick what you received", text)
        self.assertIn("Signature", text)

    def test_the_form_shows_the_day_it_was_made(self):
        picking = self._delivery()
        text = visible_text(self._page(picking).text)
        self.assertIn(picking._dispatch_date(picking.dispatch_form_date), text)
        self.assertIn("Not yet", text, "it claims to be signed already")

    # --- signing it -----------------------------------------------------------

    def test_signing_records_the_name_the_time_and_the_drawing(self):
        picking = self._delivery()
        self._sign(picking)
        picking.invalidate_recordset()

        self.assertEqual(picking.dispatch_signed_by, "Jane Customer")
        self.assertTrue(picking.dispatch_signed_on)
        self.assertEqual(picking.dispatch_state, "signed")
        self.assertEqual(base64.b64decode(picking.dispatch_signature),
                         base64.b64decode(PNG))

    def test_both_dates_are_on_the_signed_form(self):
        """The two the owner asked for: when it was made, and when it was
        signed. The gap between them is the only honest answer to when the
        customer actually got it."""
        picking = self._delivery()
        self._sign(picking)
        picking.invalidate_recordset()
        text = visible_text(self._page(picking).text)

        self.assertIn(picking._dispatch_date(picking.dispatch_form_date), text)
        self.assertIn(picking._dispatch_date(picking.dispatch_signed_on), text)
        self.assertIn("Jane Customer", text)

    def test_each_item_is_confirmed_one_at_a_time(self):
        picking = self._delivery()
        lines = picking._dispatch_lines()
        self._sign(picking, items=lines[:1])

        self.assertTrue(lines[0].dispatch_received)
        self.assertFalse(lines[1].dispatch_received,
                         "an item nobody ticked was recorded as received")

    def test_what_was_not_received_is_named_in_the_order_log(self):
        """The line somebody has to deal with tomorrow."""
        picking = self._delivery()
        lines = picking._dispatch_lines()
        self._sign(picking, items=lines[:1])

        log = " ".join(picking.message_ids.mapped("body"))
        self.assertIn("Delivery confirmed and signed by Jane Customer", log)
        self.assertIn("Not confirmed by the customer", log)
        self.assertIn(lines[1].product_id.name, log)

    def test_the_signature_can_be_seen_through_the_same_link(self):
        picking = self._delivery()
        self._sign(picking)
        response = self.url_open(
            "/delivery/%s/signature.png" % picking.dispatch_access_token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "image/png")
        self.assertEqual(response.content, base64.b64decode(PNG))

    # --- and what it refuses --------------------------------------------------

    def test_it_will_not_be_signed_without_a_name(self):
        picking = self._delivery()
        response = self._sign(picking, name="   ")
        picking.invalidate_recordset()

        self.assertFalse(picking.dispatch_signed_on)
        self.assertIn("type your name", visible_text(response.text))

    def test_it_will_not_be_signed_without_a_signature(self):
        picking = self._delivery()
        response = self._sign(picking, signature="")
        picking.invalidate_recordset()

        self.assertFalse(picking.dispatch_signed_on)
        self.assertIn("sign in the box", visible_text(response.text))

    def test_it_will_not_take_anything_but_a_drawing(self):
        """A public route that stores what it is given is a public route that
        stores anything."""
        picking = self._delivery()

        for bad in ("data:text/html;base64,%s" % PNG,
                    "javascript:alert(1)",
                    "data:image/png;base64,<script>"):
            self._sign(picking, signature=bad)
            picking.invalidate_recordset()
            self.assertFalse(picking.dispatch_signed_on, bad)

    def test_nothing_ticked_is_not_a_delivery(self):
        picking = self._delivery()
        response = self._sign(picking, items=picking.browse())
        picking.invalidate_recordset()

        self.assertFalse(picking.dispatch_signed_on)
        self.assertIn("tick the items", visible_text(response.text))

    def test_it_cannot_be_signed_twice(self):
        """A receipt that can be rewritten is not a receipt."""
        picking = self._delivery()
        self._sign(picking, name="Jane Customer")
        picking.invalidate_recordset()
        first = picking.dispatch_signed_on

        self._sign(picking, name="Somebody Else")
        picking.invalidate_recordset()

        self.assertEqual(picking.dispatch_signed_by, "Jane Customer")
        self.assertEqual(picking.dispatch_signed_on, first)

    def test_a_signed_form_offers_nothing_to_press(self):
        picking = self._delivery()
        self._sign(picking)
        text = visible_text(self._page(picking).text)

        self.assertIn("Received", text)
        self.assertNotIn("Confirm this delivery", text)

    def test_the_link_is_kept_from_people_the_secret_is_kept_from(self):
        picking = self._delivery()
        nobody = self.env["res.users"].create({
            "name": "Accounts", "login": "delivery-accounts",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })

        with self.assertRaises(AccessError):
            picking.with_user(nobody).dispatch_access_token

        with self.assertRaises(AccessError):
            picking.with_user(nobody).dispatch_url

        # Not asserted: that the same user can still read the rest of the
        # order. They cannot read a transfer at all - stock keeps its own
        # records to its own people - so there is nothing here to prove.

    def test_the_times_are_the_shops_and_say_which_clock_they_are(self):
        picking = self._delivery()
        shown = picking._dispatch_date(picking.dispatch_form_date)

        self.assertTrue(shown.endswith(("UTC", "EST", "EDT", "CET", "CEST")),
                        "the time does not say what clock it is on: %r" % shown)
        self.assertIn(shown, visible_text(self._page(picking).text))

    def _boxes(self, page):
        """The checkbox tags on the page, as written."""
        return re.findall(r"<input[^>]*type=.checkbox[^>]*>", page)

    def _buttons(self, page):
        """The per-group Confirm all buttons, by their own markup.

        NOT A SUBSTRING COUNT OF THE WHOLE PAGE: it carries a stylesheet and a
        script that both name confirm-all, so counting the word measures the
        page's source rather than what it offers anybody.
        """
        return re.findall(r'class="clear confirm-all"', page)

    def test_nothing_is_ticked_before_the_customer_ticks_it(self):
        """A receipt that arrives pre-ticked is one somebody confirms without
        reading it."""
        picking = self._delivery()
        boxes = self._boxes(self._page(picking).text)

        self.assertTrue(boxes, "the form offers nothing to tick")
        self.assertFalse([box for box in boxes if "checked" in box],
                         "the form confirmed the delivery for them")

    # --- one button per kind of thing ----------------------------------------

    def _everything(self):
        return self._delivery(((self.hinge, 4), (self.track, 2),
                               (self.cable, 2), (self.spring, 1)))

    def test_the_list_is_split_the_way_the_floor_splits_it(self):
        picking = self._everything()
        groups = {page: [item["name"] for item in items]
                  for page, items in picking._dispatch_groups()}

        self.assertEqual(list(groups), ["Tracks", "Springs", "Cables",
                                        "Hardware"])
        self.assertEqual(groups["Tracks"], [self.track.display_name])
        self.assertEqual(groups["Springs"], [self.spring.display_name])
        self.assertEqual(groups["Cables"], [self.cable.display_name])
        self.assertEqual(groups["Hardware"], [self.hinge.display_name])

    def test_every_group_gets_a_button_of_its_own(self):
        """Eleven lengths of track are one answer, not eleven."""
        picking = self._everything()
        page = self._page(picking).text

        self.assertEqual(len(self._buttons(page)), 4)

        for heading in ("Tracks", "Springs", "Cables", "Hardware"):
            self.assertIn("<h2>%s</h2>" % heading, page)

    def test_a_delivery_of_one_kind_has_one_group(self):
        picking = self._delivery(((self.track, 2),))
        self.assertEqual([group[0] for group in picking._dispatch_groups()],
                         ["Tracks"])
        self.assertEqual(len(self._buttons(self._page(picking).text)), 1)

    def test_the_buttons_tick_nothing_on_their_own(self):
        """They are a convenience for the customer, not a default."""
        picking = self._everything()
        boxes = self._boxes(self._page(picking).text)

        self.assertEqual(len(boxes), 4)
        self.assertFalse([box for box in boxes if "checked" in box])

    def test_signing_still_records_each_item_one_at_a_time(self):
        """Whatever the buttons do in the browser, the server is told about
        boxes and nothing else."""
        picking = self._everything()
        lines = picking._dispatch_lines()
        tracks = lines.filtered(lambda move: move.product_id == self.track)

        self._sign(picking, items=tracks)

        self.assertTrue(tracks.dispatch_received)
        self.assertFalse((lines - tracks).filtered("dispatch_received"))

    # --- a cable is one thing, however it is made ----------------------------

    def _made_up_cable(self):
        """A delivery carrying a cable the way a cable actually ships.

        FOUR MOVES AGAINST ONE ORDER LINE - the reel, the sleeve, the thimble
        and the stop - which is what a kit product explodes into. The customer
        bought one made-up cable.
        """
        parts = [
            self.env["product.product"].create({
                "name": name, "type": "consu", "is_storable": True,
                "list_price": 2.0})
            for name in ('1/8" 7X19 GAC (500 FT REEL)', "Oval Sleeve 1/8",
                         "Thimble 1/8", "Cable Stop 1/8")
        ]
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": self.cable.id,
                                   "product_uom_qty": 2})],
        })
        sale_line = order.order_line[:1]
        picking = self._delivery(((self.hinge, 4),))
        source = picking.location_id
        destination = picking.location_dest_id

        for part in parts:
            self.env["stock.move"].create({
                "picking_id": picking.id,
                "product_id": part.id,
                "product_uom_qty": 2,
                "sale_line_id": sale_line.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
            })

        picking.action_confirm()

        return picking

    def test_a_made_up_cable_is_one_row_and_not_its_parts(self):
        """THE BUG: the form asked the customer to tick a thimble."""
        picking = self._made_up_cable()
        names = [item["name"] for item in picking._dispatch_items()]

        self.assertIn(self.cable.display_name, names)
        self.assertNotIn("Thimble 1/8", names)
        self.assertNotIn('1/8" 7X19 GAC (500 FT REEL)', names)
        self.assertEqual(len(names), 2, names)

    def test_the_cable_row_is_the_quantity_that_was_bought(self):
        picking = self._made_up_cable()
        cable = [item for item in picking._dispatch_items()
                 if item["name"] == self.cable.display_name][0]

        self.assertEqual(cable["quantity"], 2)
        self.assertEqual(len(cable["moves"]), 4, "it lost its parts")

    def test_the_cable_groups_with_the_cables(self):
        picking = self._made_up_cable()
        groups = {page: [item["name"] for item in items]
                  for page, items in picking._dispatch_groups()}

        self.assertEqual(groups.get("Cables"), [self.cable.display_name])

    def test_one_tick_confirms_every_part_of_it(self):
        picking = self._made_up_cable()
        cable = [item for item in picking._dispatch_items()
                 if item["name"] == self.cable.display_name][0]

        self._sign(picking, items=[cable])

        self.assertTrue(all(move.dispatch_received for move in cable["moves"]),
                        "a part of the cable was left unconfirmed")
        self.assertFalse(
            picking._dispatch_lines().filtered(
                lambda move: move.product_id == self.hinge
            ).dispatch_received)

    def test_the_log_names_the_cable_rather_than_its_parts(self):
        picking = self._made_up_cable()
        self._sign(picking)
        log = " ".join(picking.message_ids.mapped("body"))

        self.assertIn(self.cable.display_name, log)
        self.assertNotIn("Thimble", log)
