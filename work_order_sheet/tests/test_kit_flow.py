import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestKitDoorIsSaved(HttpCase):
    """The door entered on a kit page has to survive onto the order.

    The owner's reading of it: the figures are sent off to price springs,
    tracks and cables and are never written down, so the work order sheet has
    nothing to print. This drives the real routes - the kit page's pricing
    call, then the shop's add-to-cart - and reads the order afterwards.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        attribute = self.env["product.attribute"].create({
            "name": "Add to Your Order",
            "create_variant": "no_variant",
            "display_type": "multi",
            "value_ids": [(0, 0, {"name": n}) for n in ("Springs", "Tracks", "Cables")],
        })
        self.kit = self.env["product.template"].create({
            "name": "AA-1200 Hardware Kit",
            "default_code": "AA-1200",
            "type": "consu",
            "is_storable": True,
            "list_price": 293.97,
            "is_published": True,
            "aa_dealer_quick_order": True,
            "attribute_line_ids": [(0, 0, {
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, attribute.value_ids.ids)],
            })],
        })
        self.springs_ptav = self.kit.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.name == "Springs")

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, route)

        return response.json()

    def test_the_door_reaches_the_order_line(self):
        """What the owner asked for: the figures saved, not only used."""
        door = {
            "width": "9' 0\"", "height": "7' 0\"",
            "width_in": 108, "height_in": 84,
            "weight": "300", "track_type": "3-15R",
            "lift_type": "highlift", "high_lift": 12, "drum": "",
        }
        priced = self._rpc("/aa/kit/extras", {
            "template_id": self.kit.id,
            "ptav_ids": [self.springs_ptav.id],
            "door": door,
            "qty": 1,
        })
        self.assertNotIn("error", priced.get("result", {}), priced)

        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_id.id,
            "quantity": 1,
            "no_variant_attribute_value_ids": [self.springs_ptav.id],
        })

        order = self.env["sale.order"].search(
            [("order_line.product_id", "=", self.kit.product_variant_id.id)],
            order="id desc", limit=1)
        self.assertTrue(order, "the kit never reached a cart")

        kit_line = order.order_line.filtered(
            lambda l: l.product_id == self.kit.product_variant_id)[:1]
        self.assertTrue(kit_line, "no kit line on the order")

        text = kit_line.name or ""
        self.assertIn("300 lb", text, "the door weight was not written down")
        self.assertTrue("W 9' 0\"" in text or 'W 108"' in text,
                        "the door width was not written down: %r" % text)
        self.assertTrue("H 7' 0\"" in text or 'H 84"' in text,
                        "the door height was not written down: %r" % text)

    def test_the_sheet_can_read_what_was_saved(self):
        door = {
            "width": "9' 0\"", "height": "7' 0\"",
            "width_in": 108, "height_in": 84,
            "weight": "300", "track_type": "3-15R",
            "lift_type": "highlift", "high_lift": 12, "drum": "",
        }
        self._rpc("/aa/kit/extras", {
            "template_id": self.kit.id, "ptav_ids": [self.springs_ptav.id],
            "door": door, "qty": 1})
        self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_id.id,
            "quantity": 1,
            "no_variant_attribute_value_ids": [self.springs_ptav.id]})

        order = self.env["sale.order"].search(
            [("order_line.product_id", "=", self.kit.product_variant_id.id)],
            order="id desc", limit=1)
        kit_line = order.order_line.filtered(
            lambda l: l.product_id == self.kit.product_variant_id)[:1]

        facts = self.env["stock.picking"]._work_order_dealer_door(kit_line.name or "")
        self.assertEqual(facts.get("weight"), "300 lb")
        self.assertTrue(facts.get("width"), "no width for the sheet: %r" % facts)
        self.assertTrue(facts.get("height"), "no height for the sheet: %r" % facts)

    def test_a_kit_cannot_be_added_without_its_door(self):
        """WHICH IS WHY THE DOOR IS ALWAYS THERE WHEN THE KIT IS.

        With an extra ticked and no door in the session, the server refuses the
        add outright - so a kit in a cart has, by construction, had its door
        priced first. That is worth knowing: it rules out "the kit was added
        before the door arrived" as an explanation for an empty note, and
        points at what the note was built FROM instead.
        """
        result = self._rpc("/shop/cart/add", {
            "product_template_id": self.kit.id,
            "product_id": self.kit.product_variant_id.id,
            "quantity": 1,
            "no_variant_attribute_value_ids": [self.springs_ptav.id]})

        self.assertFalse(
            self.env["sale.order"].search_count(
                [("order_line.product_id", "=", self.kit.product_variant_id.id)]),
            "the kit reached a cart with no door behind it: %s" % (result,))

    def test_a_second_door_replaces_the_first_rather_than_joining_it(self):
        """A line that carried two doors would be worse than one with none."""
        for weight in ("300", "420"):
            self._rpc("/aa/kit/extras", {
                "template_id": self.kit.id,
                "ptav_ids": [self.springs_ptav.id],
                "door": {"width": "9' 0\"", "height": "7' 0\"",
                         "width_in": 108, "height_in": 84, "weight": weight,
                         "track_type": "3-15R", "lift_type": "standard",
                         "high_lift": 0, "drum": ""},
                "qty": 1})

            if weight == "300":
                self._rpc("/shop/cart/add", {
                    "product_template_id": self.kit.id,
                    "product_id": self.kit.product_variant_id.id,
                    "quantity": 1,
                    "no_variant_attribute_value_ids": [self.springs_ptav.id]})

        order = self.env["sale.order"].search(
            [("order_line.product_id", "=", self.kit.product_variant_id.id)],
            order="id desc", limit=1)
        kit_line = order.order_line.filtered(
            lambda l: l.product_id == self.kit.product_variant_id)[:1]
        kit_line.invalidate_recordset()
        text = kit_line.name or ""
        self.assertIn("420 lb", text, "the line kept the door that was replaced")
        self.assertNotIn("300 lb", text, "the line carries two doors")
