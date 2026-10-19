"""WHAT THE BOX IS FOR: the card, the sticker and the page it opens.

The owner's instruction, 2026-10-19: a button beside Start on the Hardware page
that lists the spring and its turns, the drum used in the calculation, the
colour of the hardware, the type of lift, the cable length and the track
lengths - and a sticker on the box whose QR code gives the same list to a
phone. Anything the order does not say is left out; an order with no hardware
in it shows nothing at all.

These tests go the whole way round: the real kit flow books the order, confirming
it makes the manufacturing order, and the card is read off that.
"""

import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class HardwareCardCase(HttpCase):

    # A REAL CALCULATOR SPEC, as the browser posts it - now carrying the turns
    # and the drum it was worked out on, which is the change that makes the
    # card possible at all.
    SPEC = {
        "assembly": "Duplex",
        "springs": 2,
        "drum": "CANIMEX/TF D400-96",
        "turns": 7.5,
        "cycles": "10,000",
        "doorWeight": "355",
        "doorHeight": "7' 0\"",
        "doorWidth": "9' 0\"",
        "hiLift": 0,
        "springsSpec": [
            {"role": "Outer", "wire": 0.2625, "id": 6.0, "length": 32.5},
            {"role": "Inner", "wire": 0.2253, "id": 3.75, "length": 31.25},
        ],
    }

    DRUM_LABEL = "D400-96 (up to 530 lb)"
    OTHER_DRUM = "D400-144 (up to 750 lb)"

    def setUp(self):
        super().setUp()
        extras = self.env["product.attribute"].create({
            "name": "Add to Your Order",
            "create_variant": "no_variant",
            "display_type": "multi",
            "value_ids": [(0, 0, {"name": n}) for n in ("Springs", "Tracks", "Cables")],
        })
        drum = self.env["product.attribute"].create({
            "name": "Drum",
            "create_variant": "always",
            "value_ids": [(0, 0, {"name": self.DRUM_LABEL}),
                          (0, 0, {"name": self.OTHER_DRUM})],
        })
        # THE FINISH IS AN ATTRIBUTE, as it is in the real catalogue - "colour
        # of hardware" is read off the kit variant rather than guessed from
        # its name.
        colour = self.env["product.attribute"].create({
            "name": "Finish Color",
            "create_variant": "always",
            "value_ids": [(0, 0, {"name": "White"}), (0, 0, {"name": "Black"})],
        })
        self.kit = self.env["product.template"].create({
            "name": "AA-1200 Hardware Kit",
            "default_code": "AA-1200",
            "type": "consu",
            "is_storable": True,
            "list_price": 293.97,
            "is_published": True,
            "aa_dealer_quick_order": True,
            "attribute_line_ids": [
                (0, 0, {"attribute_id": extras.id,
                        "value_ids": [(6, 0, extras.value_ids.ids)]}),
                (0, 0, {"attribute_id": drum.id,
                        "value_ids": [(6, 0, drum.value_ids.ids)]}),
                (0, 0, {"attribute_id": colour.id,
                        "value_ids": [(6, 0, colour.value_ids.ids)]}),
            ],
        })
        values = self.kit.attribute_line_ids.product_template_value_ids
        self.springs_ptav = values.filtered(lambda v: v.name == "Springs")
        self.drum_ptav = values.filtered(lambda v: v.name == self.DRUM_LABEL)
        self.other_drum_ptav = values.filtered(lambda v: v.name == self.OTHER_DRUM)
        self.white_ptav = values.filtered(lambda v: v.name == "White")
        self.door = {
            "width": "9' 0\"", "height": "7' 0\"",
            "width_in": 108, "height_in": 84,
            "weight": "355", "track_type": "3-15R",
            "lift_type": "standard", "high_lift": "", "drum": "D400-96",
            "spring_spec": self.SPEC, "spring_warnings": [],
        }

    # --- the kit flow, as the shop page runs it ------------------------------

    def _variant(self, drum_ptav):
        variant = self.kit.product_variant_ids.filtered(
            lambda v: drum_ptav in v.product_template_attribute_value_ids
            and self.white_ptav in v.product_template_attribute_value_ids)[:1]
        self.assertTrue(variant, "no variant for that drum and finish")

        return variant

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, route)

        return response.json()

    def _order_a_kit(self, drum_ptav=None, door=None):
        """Price a door, then put its kit in the cart. Returns the order."""
        drum_ptav = drum_ptav or self.drum_ptav
        variant = self._variant(drum_ptav)
        priced = self._rpc("/aa/kit/extras", {
            "template_id": self.kit.id,
            "ptav_ids": [self.springs_ptav.id, drum_ptav.id, self.white_ptav.id],
            "door": door or self.door,
            "qty": 1})
        self.assertNotIn("error", priced.get("result", {}), priced)

        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": variant.id,
            "quantity": 1,
            "no_variant_attribute_value_ids": [self.springs_ptav.id]})

        order = self.env["sale.order"].search(
            [("order_line.product_id", "in", self.kit.product_variant_ids.ids)],
            order="id desc", limit=1)
        self.assertTrue(order, "the kit never reached a cart")
        order.invalidate_recordset()

        return order

    def _confirm(self, order):
        order.action_confirm()
        order.invalidate_recordset()

        return order

    def _kit_job(self, order):
        job = self.env["mrp.production"].search(
            [("origin", "=", order.name), ("aa_station_kind", "=", "kit")],
            order="id", limit=1)
        self.assertTrue(job, "confirming the order made no hardware job")

        return job

    def _card(self, order):
        return self._kit_job(order)._aa_hardware_card()

    @staticmethod
    def _rows(card):
        return {label: value for label, value in card.get("rows", [])}

    # --- the six facts -------------------------------------------------------

    def test_the_card_says_what_the_box_is_for(self):
        card = self._card(self._confirm(self._order_a_kit()))
        rows = self._rows(card)

        self.assertEqual(card["order"][:1], "S", card["order"])
        self.assertIn("1200", card["kit"])
        self.assertEqual(card["size"], '9\' 0" x 7\' 0"', card["size"])
        self.assertEqual(card["weight"], "355 lb")
        # The spring, both halves of it, the way the shop writes it.
        self.assertIn(".2625", rows["Spring (outer)"])
        self.assertIn('6"', rows["Spring (outer)"])
        self.assertIn('32 1/2"', rows["Spring (outer)"])
        self.assertIn(".2253", rows["Spring (inner)"])
        self.assertIn("7.5", rows["Turns"])
        self.assertEqual(rows["Drum"], "D400-96")
        self.assertEqual(rows["Colour"], "White")
        self.assertEqual(rows["Lift"], "Standard")

    def test_the_turns_reach_the_order_from_the_calculator(self):
        """THE CHANGE THAT MAKES THE CARD POSSIBLE. Turns are worked out in
        the browser from a fitted curve and were thrown away at the door."""
        order = self._order_a_kit()
        spring = order.order_line.filtered("spring_spec_json")[:1]
        self.assertTrue(spring, "the kit booked no spring")
        spec = json.loads(spring.spring_spec_json)
        self.assertEqual(spec["turns"], 7.5)
        self.assertEqual(spec["drum"], "CANIMEX/TF D400-96")

    def test_the_drum_is_still_not_written_on_the_spring(self):
        """It is ours to know, says the rule the spring description follows,
        and carrying the drum as data beside it does not change that.

        The kit variant's OWN name does name the drum - "Option for: AA-1200
        Hardware Kit (D400-96 ...)" - and always has. What this holds is that
        nothing added a drum of its own to the specification underneath it.
        """
        order = self._order_a_kit()
        spring = order.order_line.filtered("spring_spec_json")[:1]
        spec_lines = [line for line in (spring.name or "").split("\n")
                      if not line.startswith("Option for:")]
        self.assertFalse([line for line in spec_lines if "D400" in line],
                         spring.name)

    def test_the_hand_is_counted(self):
        card = self._card(self._confirm(self._order_a_kit()))
        self.assertEqual(self._rows(card)["Wind"], "1 LH, 1 RH")

    # --- what the order never said ------------------------------------------

    def test_a_fact_the_order_does_not_hold_is_left_out(self):
        """No cable and no track were ordered, so the card says nothing about
        either - rather than "Cable: -"."""
        rows = self._rows(self._card(self._confirm(self._order_a_kit())))
        self.assertNotIn("Cable", rows)
        self.assertNotIn("Track", rows)

    def test_an_order_with_no_hardware_shows_nothing(self):
        """A spring on its own. Its own job is at the Springs station and has
        no card, and nothing else on the order does either."""
        order = self._order_a_kit()
        kit = order.order_line.filtered(
            lambda line: line.product_id.product_tmpl_id == self.kit)
        spring = order.order_line.filtered("spring_spec_json")
        spring.linked_line_id = False
        kit.unlink()
        self._confirm(order)
        jobs = self.env["mrp.production"].search([("origin", "=", order.name)])
        self.assertTrue(jobs, "the spring made no job at all")

        for job in jobs:
            self.assertEqual(job._aa_hardware_card(), {}, job.aa_station_kind)
            self.assertFalse(job.aa_hardware_card)

    # --- the cable and the track --------------------------------------------

    def _add_cable_and_track(self, order):
        """A prepared cable pair and two tracks, hung on the kit line."""
        kit = order.order_line.filtered(
            lambda line: line.product_id.product_tmpl_id == self.kit)[:1]
        reel = self.env["product.product"].create({
            "name": '1/8" 7x19 Cable 500ft Reel', "type": "consu"})
        cable = self.env["product.product"].create({
            "name": 'Lift Cable 1/8" Pair - Prepared (7\' Door, 3" Track (15R))',
            "type": "consu", "is_storable": True})
        # The reel quantity is for the PAIR, so one cable is half of it: 29
        # feet of reel is two cables of 14' 6".
        self.env["mrp.bom"].create({
            "product_tmpl_id": cable.product_tmpl_id.id,
            "type": "phantom",
            "product_qty": 1.0,
            "bom_line_ids": [(0, 0, {"product_id": reel.id, "product_qty": 29.0})],
        })
        tracks = self.env["product.product"].create([
            {"name": '3" Vertical Track 76" - 7\' Door Height White', "type": "consu"},
            {"name": '3" Horizontal Track -  96" White', "type": "consu"},
        ])

        for product in cable | tracks:
            self.env["sale.order.line"].create({
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1,
                "linked_line_id": kit.id,
            })

        order.invalidate_recordset()

        return order

    def test_the_cable_and_the_tracks_are_measured(self):
        order = self._add_cable_and_track(self._order_a_kit())
        rows = self._rows(self._card(self._confirm(order)))
        # Two cables, each half of the 29 feet of reel the pair takes.
        self.assertEqual(rows["Cable"], '1/8" - 2 x 174"', rows["Cable"])
        self.assertEqual(rows["Track"], '3" Vertical 76" · 3" Horizontal 96"',
                         "the cable is named for the track it suits, so a "
                         "loose read for the word finds it")

    def test_a_cable_with_no_length_set_says_only_what_it_is(self):
        """A pair whose BoM nobody has filled in has no cut length, and a
        length nobody set is not a length to print on a box."""
        order = self._order_a_kit()
        kit = order.order_line.filtered(
            lambda line: line.product_id.product_tmpl_id == self.kit)[:1]
        cable = self.env["product.product"].create({
            "name": 'Lift Cable 5/32" Pair - Prepared (8\' Door, 3" Track (15R))',
            "type": "consu"})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": cable.id,
            "product_uom_qty": 1, "linked_line_id": kit.id})
        order.invalidate_recordset()
        rows = self._rows(self._card(self._confirm(order)))
        self.assertEqual(rows["Cable"], '5/32"')

    # --- two doors on one order ---------------------------------------------

    def test_two_doors_do_not_share_a_card(self):
        """"One door per card": each kit's card carries its own door, and says
        which of how many it is."""
        order = self._order_a_kit()
        tall = dict(self.door, height="8' 0\"", height_in=96, weight="420",
                    drum="D400-144",
                    spring_spec=dict(self.SPEC, doorHeight="8' 0\"",
                                     doorWeight="420", turns=8.1,
                                     drum="CANIMEX/TF D400-144"))
        self._order_a_kit(drum_ptav=self.other_drum_ptav, door=tall)
        order.invalidate_recordset()
        self._confirm(order)
        jobs = self.env["mrp.production"].search(
            [("origin", "=", order.name), ("aa_station_kind", "=", "kit")],
            order="id")
        self.assertEqual(len(jobs), 2, "one hardware job per kit")
        cards = [job._aa_hardware_card() for job in jobs]
        self.assertEqual([card["door"] for card in cards],
                         ["Door 1 of 2", "Door 2 of 2"])
        self.assertEqual([card["weight"] for card in cards],
                         ["355 lb", "420 lb"])
        self.assertEqual([self._rows(card)["Turns"][:3] for card in cards],
                         ["7.5", "8.1"])
        self.assertEqual([self._rows(card)["Drum"] for card in cards],
                         ["D400-96", "D400-144"])

    # --- the sticker and the page it opens -----------------------------------

    def test_the_sticker_link_opens_the_page(self):
        job = self._kit_job(self._confirm(self._order_a_kit()))
        response = self.url_open("/box/%d/%s" % (job.id, job._aa_box_token()))
        self.assertEqual(response.status_code, 200)
        page = response.text
        self.assertIn("7.5", page)
        self.assertIn("D400-96", page)
        self.assertIn("White", page)

    def test_a_wrong_token_opens_nothing(self):
        job = self._kit_job(self._confirm(self._order_a_kit()))

        for token in ("", "x", "0" * 64, job._aa_box_token()[:-1] + "0"):
            response = self.url_open("/box/%d/%s" % (job.id, token or "-"))
            self.assertEqual(response.status_code, 404, token)

    def test_one_box_s_link_does_not_open_another(self):
        order = self._order_a_kit()
        self._order_a_kit(drum_ptav=self.other_drum_ptav)
        order.invalidate_recordset()
        self._confirm(order)
        first, second = self.env["mrp.production"].search(
            [("origin", "=", order.name), ("aa_station_kind", "=", "kit")],
            order="id")
        response = self.url_open("/box/%d/%s" % (second.id, first._aa_box_token()))
        self.assertEqual(response.status_code, 404)

    def test_the_link_is_the_same_one_tomorrow(self):
        """A sticker printed today has to open next week, so the token is
        derived rather than rolled."""
        job = self._kit_job(self._confirm(self._order_a_kit()))
        token = job._aa_box_token()
        job.invalidate_recordset()
        self.assertEqual(job._aa_box_token(), token)
        self.assertIn(token, job.aa_box_url)

    def test_the_sticker_prints_what_the_card_says(self):
        job = self._kit_job(self._confirm(self._order_a_kit()))
        html = self.env["ir.actions.report"]._render_qweb_html(
            "aa_shop_floor.report_hardware_sticker", job.ids)[0].decode()
        self.assertIn("D400-96", html)
        self.assertIn("7.5", html)
        self.assertIn("/report/barcode/", html)
        self.assertIn("barcode_type=QR", html)

    def test_the_sticker_is_a_four_by_six_label(self):
        """IT HAS TO COME OUT OF A LABEL PRINTER. Rendering it proves the
        paper format is attached and that wkhtmltopdf can lay the page out at
        4 x 6 - a report that only ever rendered as HTML in a test would be
        found out on the printer."""
        job = self._kit_job(self._confirm(self._order_a_kit()))
        report = self.env.ref("aa_shop_floor.action_report_hardware_sticker")
        self.assertEqual(report.paperformat_id.page_width, 101)
        self.assertEqual(report.paperformat_id.page_height, 152)
        # Odoo renders reports as HTML under test unless it is told the point
        # of the test is the PDF.
        pdf, kind = report.with_context(
            force_report_rendering=True)._render_qweb_pdf(
                report.report_name, job.ids)
        self.assertEqual(kind, "pdf")
        self.assertTrue(pdf.startswith(b"%PDF"), pdf[:20])

    def test_a_job_with_nothing_to_say_prints_no_figures(self):
        """The report is bound to every manufacturing order, so somebody will
        print it for one that is not a hardware box."""
        job = self.env["mrp.production"].search(
            [("aa_station_kind", "!=", "kit")], limit=1) \
            or self.env["mrp.production"].create({
                "product_id": self.env["product.product"].create({
                    "name": "Something else", "type": "consu",
                    "is_storable": True}).id})
        html = self.env["ir.actions.report"]._render_qweb_html(
            "aa_shop_floor.report_hardware_sticker", job.ids)[0].decode()
        self.assertIn("nothing to put on a sticker", html)
