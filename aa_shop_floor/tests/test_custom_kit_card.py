"""WHAT A CUSTOM KIT'S BENCH CARD SAYS.

The owner, 2026-10-22: "custom kits dont make manufacturing orders correctly,
work orders show up and so does the changes in inventory, but on the shop
floor, it only makes one assignment and the only thing on it says custom kit".

ONE ASSIGNMENT IS RIGHT - a custom kit is one kit, packed at one bench, in one
box. What was wrong is what the card said, and reproducing it took one order:

    CARD for WH/MO/02330:
    Kit|Custom Kit

and nothing else. The card built its box contents by exploding the kit's
PHANTOM BOM, and a custom kit has none: its contents are the order's own lines
(CLAUDE.md, owner 2026-10-20 - "the only difference is that its contents are
the order's own lines rather than a phantom BoM"). So the bench was handed a
box with nothing in it to pack.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class CustomKitCardCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Kit buyer"})
        self.custom_kit = self.env.ref("aa_dealer_orders.product_custom_kit")

    def _part(self, name, price=2.0):
        return self.env["product.template"].create({
            "name": name, "type": "consu", "is_storable": True,
            "list_price": price, "sale_ok": True}).product_variant_id

    def _custom_kit_order(self, parts, quantity=1.0):
        """A custom kit line with its parts linked to it, as the page books
        them: linked_line_id is written by the dealer Quick Order."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        kit_line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.custom_kit.product_variant_id.id,
            "product_uom_qty": quantity})

        for variant, qty in parts:
            self.env["sale.order.line"].create({
                "order_id": order.id, "product_id": variant.id,
                "product_uom_qty": qty, "linked_line_id": kit_line.id})

        order.action_confirm()

        return order, kit_line

    def _job(self, order):
        return self.env["mrp.production"].search([("origin", "=", order.name)])

    def _card(self, job):
        return job.aa_shop_spec or ""

    # --- the report -------------------------------------------------------

    def test_a_custom_kit_card_lists_what_goes_in_the_box(self):
        """HIS REPORT. The card said "Kit: Custom Kit" and stopped."""
        top = self._part("Top Bracket White")
        hinge = self._part("Center Hinge White")
        order, _kit_line = self._custom_kit_order([(top, 2), (hinge, 8)])

        job = self._job(order)
        card = self._card(job)

        self.assertEqual(len(job), 1, "a custom kit is one kit at one bench")
        self.assertIn("Box contents", card, card)
        self.assertIn("Top Bracket White|2", card, card)
        self.assertIn("Center Hinge White|8", card, card)

    def test_every_piece_is_tickable(self):
        """"Put it in the box, tick it" (owner, 2026-10-14) - the pieces of a
        custom kit are checked off like any other kit's."""
        order, _kit_line = self._custom_kit_order([(self._part("Shaft Key"), 4)])

        card = self._card(self._job(order))

        self.assertIn("Shaft Key|4|c", card, card)

    def test_a_catalogue_kit_still_reads_its_phantom_bom(self):
        """The guard: this must not change how an AA kit's card is built."""
        piece = self._part("Canimex D400-96 White")
        kit = self.env["product.template"].create({
            "name": "AA-1200 Hardware Kit", "type": "consu",
            "is_storable": True, "list_price": 100.0, "sale_ok": True})
        self.env["mrp.bom"].create({
            "product_tmpl_id": kit.id, "type": "phantom",
            "bom_line_ids": [(0, 0, {"product_id": piece.id, "product_qty": 2})]})
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": kit.product_variant_id.id,
                "product_uom_qty": 1})]})
        order.action_confirm()

        card = self._card(self._job(order))

        self.assertIn("Box contents", card, card)
        self.assertIn("Canimex D400-96 White|2", card, card)

    def test_another_kit_s_parts_do_not_leak_into_this_box(self):
        """Two custom kits on one order, each with its own parts. The line
        says which kit it belongs to and that is what is read."""
        mine = self._part("Top Bracket White")
        theirs = self._part("Bottom Bracket White")
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        first = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.custom_kit.product_variant_id.id,
            "product_uom_qty": 1})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": mine.id,
            "product_uom_qty": 2, "linked_line_id": first.id})
        second = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.custom_kit.product_variant_id.id,
            "product_uom_qty": 1})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": theirs.id,
            "product_uom_qty": 5, "linked_line_id": second.id})
        order.action_confirm()

        jobs = self.env["mrp.production"].search(
            [("origin", "=", order.name)], order="id")
        self.assertEqual(len(jobs), 2, "one job per kit")

        first_card = self._card(jobs.filtered(
            lambda j: j.aa_sale_line_id == first))
        second_card = self._card(jobs.filtered(
            lambda j: j.aa_sale_line_id == second))

        self.assertIn("Top Bracket White|2", first_card, first_card)
        self.assertNotIn("Bottom Bracket", first_card, first_card)
        self.assertIn("Bottom Bracket White|5", second_card, second_card)
        self.assertNotIn("Top Bracket", second_card, second_card)

    def test_a_custom_kit_with_no_parts_still_names_itself(self):
        """An empty custom kit is a page that went wrong, not a crash."""
        order, _kit_line = self._custom_kit_order([])

        card = self._card(self._job(order))

        self.assertIn("Kit|Custom Kit", card, card)
        self.assertNotIn("Box contents", card, card)
