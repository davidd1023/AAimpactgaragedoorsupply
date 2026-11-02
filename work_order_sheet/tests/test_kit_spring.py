import json

from odoo.tests.common import HttpCase, tagged

from .test_work_order_sheet import visible_text


@tagged("post_install", "-at_install")
class TestKitSpring(HttpCase):
    """A kit ordered with the Springs option prints like a calculator one.

    THE BUG ALL OF THIS GUARDS. `sale.order.line.name` is a stored COMPUTED
    field - core recomputes it from the product whenever product_id,
    linked_line_id or linked_line_ids changes. Adding a kit's extras links them
    to the kit line, so both of the last two change, and everything written
    into those descriptions was thrown away a line later:

      * the spring's specification, leaving the floor an assembly with no
        wire, no length and no door, filed under Hardware because nothing in
        the text said it was a spring;
      * the dealer kit's door note, which is the only record of the door.

    The calculator's own spring was never affected - it is linked to nothing -
    which is exactly why this looked like a kit problem for so long.
    """

    # SINGLE, not the Duplex this carried until 2026-10-28. A duplex is no
    # longer sold - "we do not currently manufacture custom duplex springs" -
    # so the kit's own pricing route refuses one and this fixture was quoting
    # the refusal rather than booking a spring. `springs: 2` is still two
    # springs on the DOOR, a left and a right; what has gone is the NEST.
    #
    # Missed when the other four fixtures were converted that morning,
    # because only spring_engineering, aa_shop_floor and aa_dealer_orders
    # were run - not this module.
    SPEC = {
        "assembly": "Single",
        "springs": 2,
        "drum": "CANIMEX/TF D400-96",
        "cycles": "10,000",
        "doorWeight": "355",
        "doorHeight": "7' 0\"",
        "doorWidth": "9' 0\"",
        "hiLift": 0,
        "springsSpec": [
            {"role": "Spring", "wire": 0.2625, "id": 6.0, "length": 32.5},
        ],
    }

    # THE DRUM'S OWN RATING, which is what the sheet used to print as the door
    # weight. These labels are the shop's, written by kit_setup.
    DRUM_LABEL = 'D400-96 (up to 530 lb)'

    def setUp(self):
        super().setUp()
        extras = self.env["product.attribute"].create({
            "name": "Add to Your Order",
            "create_variant": "no_variant",
            "display_type": "multi",
            "value_ids": [(0, 0, {"name": n}) for n in ("Springs", "Tracks", "Cables")],
        })
        # TWO VALUES, so the choice is a real one: Odoo leaves an attribute
        # with a single possible value out of the variant's display name, and
        # the whole point here is that the chosen drum's label - rating and all
        # - lands in the order line's description.
        drum = self.env["product.attribute"].create({
            "name": "Drum",
            "create_variant": "always",
            "value_ids": [(0, 0, {"name": self.DRUM_LABEL}),
                          (0, 0, {"name": 'D400-144 (up to 750 lb)'})],
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
            ],
        })
        values = self.kit.attribute_line_ids.product_template_value_ids
        self.springs_ptav = values.filtered(lambda v: v.name == "Springs")
        self.drum_ptav = values.filtered(lambda v: v.name == self.DRUM_LABEL)
        self.variant = self.kit.product_variant_ids.filtered(
            lambda v: self.drum_ptav in v.product_template_attribute_value_ids)[:1]
        self.assertTrue(self.variant, "no variant for that drum")
        self.door = {
            "width": "9' 0\"", "height": "7' 0\"",
            "width_in": 108, "height_in": 84,
            "weight": "355", "track_type": "3-15R",
            "lift_type": "standard", "high_lift": "", "drum": "D400-96",
            "spring_spec": self.SPEC, "spring_warnings": [],
        }

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, route)

        return response.json()

    def _order_a_kit(self):
        """The real flow: price the door, then add the kit to the cart."""
        priced = self._rpc("/aa/kit/extras", {
            "template_id": self.kit.id,
            "ptav_ids": [self.springs_ptav.id, self.drum_ptav.id],
            "door": self.door,
            "qty": 1})
        self.assertNotIn("error", priced.get("result", {}), priced)

        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.variant.id,
            "quantity": 1,
            "no_variant_attribute_value_ids": [self.springs_ptav.id]})

        order = self.env["sale.order"].search(
            [("order_line.product_id", "=", self.variant.id)],
            order="id desc", limit=1)
        self.assertTrue(order, "the kit never reached a cart")
        order.invalidate_recordset()

        return order

    def _lines(self, order):
        kit = order.order_line.filtered(lambda l: l.product_id == self.variant)[:1]
        spring = order.order_line.filtered(
            lambda l: l.product_id.name == "Custom Torsion Spring Assembly")[:1]

        return kit, spring

    # --- what the order itself keeps -----------------------------------------

    def test_the_spring_keeps_its_specification(self):
        """THE BUG: linking the spring to its kit wiped the specification."""
        order = self._order_a_kit()
        _kit, spring = self._lines(order)
        self.assertTrue(spring, "the kit booked no spring assembly")

        text = spring.name or ""
        self.assertIn("Single, 2 springs", text)
        self.assertIn('0.2625" wire', text)
        self.assertIn('32.5" long', text)
        self.assertIn("355 lb", text)
        self.assertTrue(spring.linked_line_id,
                        "the spring is not linked to its kit, so this proves "
                        "nothing - the recompute is what the link triggers")

    def test_the_kit_keeps_its_door(self):
        order = self._order_a_kit()
        kit, _spring = self._lines(order)
        text = kit.name or ""
        self.assertIn('W 108"', text)
        self.assertIn('H 84"', text)
        self.assertIn("355 lb", text)

    def test_the_door_is_stored_as_numbers(self):
        """Not only described. Prose has to be interpreted; a number does not."""
        order = self._order_a_kit()
        kit, spring = self._lines(order)
        self.assertEqual(kit.aa_door_width_in, 108)
        self.assertEqual(kit.aa_door_height_in, 84)
        self.assertEqual(kit.aa_door_weight_lb, 355)
        self.assertEqual(spring.aa_door_weight_lb, 355)

    def test_a_description_rebuilt_again_still_carries_both(self):
        """Any later recompute - a product change, another linked line - has
        to leave the specification where it was."""
        order = self._order_a_kit()
        kit, spring = self._lines(order)
        (kit | spring).invalidate_recordset()
        (kit | spring).modified(["product_id"])
        kit.flush_recordset()
        self.assertIn("355 lb", kit.name or "")
        self.assertIn('0.2625" wire', spring.name or "")

    # --- what the sheet prints -----------------------------------------------

    def _sheet(self, order):
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertTrue(picking, "the order made no transfer")

        return picking

    def test_the_spring_prints_on_the_springs_page(self):
        picking = self._sheet(self._order_a_kit())
        pages = {s["title"]: s["lines"] for s in picking._work_order_sections()}
        self.assertIn("Springs", pages,
                      "the kit's spring did not reach a Springs page: %s"
                      % list(pages))

        spring = [line for line in pages["Springs"] if line["spring"]]
        self.assertTrue(spring, "the Springs page carries no specification")
        self.assertEqual(spring[0]["kind"], "spring")
        # ONE SPECIFICATION ROW, not two. This asserted 2 while the fixture
        # was a Duplex, where the two rows are the OUTER and the INNER of one
        # nest - not the two springs on the door, which are the same spring
        # wound each way. A Single has one row to wind from.
        self.assertEqual(len(spring[0]["spring"]["springs"]), 1)

    def test_the_door_weight_is_the_door_and_not_the_drums_rating(self):
        """THE 530 lb BUG. The Drum option is labelled with what the drum can
        carry, Odoo lists the chosen options in the description, and the first
        weight in the text won - so a 355 lb door printed as 530 lb."""
        picking = self._sheet(self._order_a_kit())
        self.assertIn(self.DRUM_LABEL,
                      " ".join(picking.move_ids.product_id.mapped("display_name")),
                      "the drum rating is not in the text, so this proves "
                      "nothing")
        door = picking._work_order_door()
        self.assertEqual(door.get("weight"), "355 lb")
        self.assertEqual(door.get("width"), "9' 0\"")
        self.assertEqual(door.get("height"), "7' 0\"")

    def test_the_printed_sheet_says_355(self):
        picking = self._sheet(self._order_a_kit())
        text = visible_text(self.env["ir.actions.report"]._render_qweb_html(
            "work_order_sheet.report_work_order_sheet", picking.ids)[0])
        self.assertIn("355 lb", text)
        self.assertNotIn("530 lb", text)
        self.assertIn('0.2625"', text)

    # --- the rating itself ----------------------------------------------------

    def test_a_rating_is_never_read_as_a_door(self):
        read = self.env["stock.picking"]._work_order_dealer_door
        self.assertEqual(
            read('[AA-1200] Kit (D400-96 (up to 530 lb))\n'
                 'Track: 3" 15R | W 108" x H 84" | 355 lb').get("weight"),
            "355 lb")
        self.assertEqual(
            read('Drum: D575-120 (high lift up to 120", up to 1,000 lb)'
                 ' | W 108" x H 84" | 355 lb').get("weight"),
            "355 lb")
        self.assertEqual(read("Drum: D400-96 (up to 530 lb)"), {})
