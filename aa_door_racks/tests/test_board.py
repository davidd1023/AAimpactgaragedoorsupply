from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBoard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Bundle = self.env["aa.door.bundle"]

    def _receive(self, doors):
        spots = self.Bundle.board_suggest(doors)["spots"]
        self.assertTrue(spots)
        return self.Bundle.board_receive(doors, spots[0])

    def test_receive_search_move_deliver(self):
        data = self.Bundle.board_data()
        self.assertEqual([s["name"] for s in data["sides"]], ["A", "B", "C", "D", "E"])
        b = self._receive([{"order_ref": "1234", "width": 96, "panels": 4},
                           {"order_ref": "1250", "width": 108, "panels": 4}])
        self.assertEqual(b["height"], 27.5)
        self.assertTrue(b["location"])
        found = self.Bundle.board_search("1250")
        self.assertEqual(found[0]["bundle"], b["id"])
        # an admin moves it
        spots = self.Bundle.board_suggest([], b["id"])["spots"]
        target = [s for s in spots if s["level_code"] != b["location"].split(" ")[0]][0]
        self.Bundle.board_move(b["id"], target)
        bundle = self.Bundle.browse(b["id"])
        self.assertEqual(bundle.level_id.id, target["level"])
        # one door delivered, the other still there; then both
        doors = bundle.door_ids
        self.Bundle.board_deliver([doors[0].id])
        self.assertEqual(bundle.state, "stored")
        self.Bundle.board_deliver([doors[1].id])
        self.assertEqual(bundle.state, "out")
        self.assertFalse(bundle.location)

    def test_remove_delivered_and_mistake(self):
        b = self._receive([{"order_ref": "R1", "width": 96, "panels": 4},
                           {"order_ref": "R2", "width": 96, "panels": 4}])
        bundle = self.Bundle.browse(b["id"])
        # one door picked up: kept in history, bundle still on the rack
        self.Bundle.board_remove(False, [bundle.door_ids[0].id], "delivered")
        self.assertEqual(bundle.door_ids[0].state, "delivered")
        self.assertEqual(bundle.state, "stored")
        # the other entered by mistake: deleted, bundle frees its spot
        mistake = bundle.door_ids.filtered(lambda d: d.state == "stored")
        self.Bundle.board_remove(False, mistake.ids, "mistake")
        self.assertFalse(mistake.exists())
        self.assertEqual(bundle.state, "out")
        self.assertFalse(self.Bundle.board_search("R2"))
        # a whole bundle entered by mistake disappears entirely
        b2 = self._receive([{"order_ref": "R3", "width": 96, "panels": 4}])
        self.Bundle.board_remove(b2["id"], [], "mistake")
        self.assertFalse(self.Bundle.browse(b2["id"]).exists())
        # a whole bundle picked up
        b3 = self._receive([{"order_ref": "R4", "width": 96, "panels": 4},
                            {"order_ref": "R5", "width": 96, "panels": 4}])
        self.Bundle.board_remove(b3["id"], [], "delivered")
        self.assertEqual(self.Bundle.browse(b3["id"]).state, "out")

    def test_mistake_needs_an_admin(self):
        from odoo.exceptions import AccessError
        b = self._receive([{"order_ref": "R9", "width": 96, "panels": 4}])
        user = self.env["res.users"].create({
            "name": "Rack clerk", "login": "rack_clerk_t",
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])]})
        with self.assertRaises(AccessError):
            self.Bundle.with_user(user).board_remove(b["id"], [], "mistake")

    def test_scan_sticker(self):
        r = self.Bundle.board_scan("AAD|1051|2|107|87.5|4", [])
        self.assertTrue(r["ok"])
        self.assertEqual((r["door"]["order_ref"], r["door"]["door_no"], r["door"]["width"], r["door"]["panels"]),
                         ("1051", 2, 107.0, 4))
        # the same door scanned twice in one bundle
        again = self.Bundle.board_scan("AAD|1051|2|107|87.5|4", [{"order_ref": "1051", "door_no": 2}])
        self.assertFalse(again["ok"])
        # a plain number that is no AA order: sizes must be typed
        plain = self.Bundle.board_scan("9999", [])
        self.assertTrue(plain["ok"])
        self.assertEqual(plain["level"], "warning")
        # received, then scanned again: warned it is already on the racks
        b = self.Bundle.board_receive([dict(r["door"])], self.Bundle.board_suggest([r["door"]])["spots"][0])
        self.assertEqual(self.Bundle.browse(b["id"]).door_ids.door_no, 2)
        warn = self.Bundle.board_scan("AAD|1051|2|107|87.5|4", [])
        self.assertIn("already on the racks", warn["msg"])
        # every suggestion says why
        spots = self.Bundle.board_suggest([r["door"]])["spots"]
        self.assertTrue(spots[0]["best"] and spots[0]["why"])

    def test_split(self):
        b = self._receive([{"order_ref": "A1", "width": 96, "panels": 4},
                           {"order_ref": "A2", "width": 96, "panels": 4}])
        door = self.Bundle.browse(b["id"]).door_ids[1]
        new = self.Bundle.board_split(door.id)
        self.assertEqual(self.Bundle.browse(b["id"]).height, 13)
        spots = self.Bundle.board_suggest([], new["id"])["spots"]
        self.Bundle.board_move(new["id"], spots[0])
        self.assertEqual(self.Bundle.browse(new["id"]).state, "stored")

    def test_dispatch_frees_the_door(self):
        partner = self.env["res.partner"].create({"name": "Dealer"})
        product = self.env["product.product"].create({"name": "Widget", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(
            product, self.env.ref("stock.warehouse0").lot_stock_id, 5)
        order = self.env["sale.order"].create({
            "partner_id": partner.id, "client_order_ref": "AA-777",
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1})]})
        order.action_confirm()
        b = self._receive([{"order_ref": "AA-777", "width": 96, "panels": 4}])
        door = self.Bundle.browse(b["id"]).door_ids
        self.assertEqual(door.sale_order_id, order)
        for picking in order.picking_ids.sorted("id"):
            if picking.state in ("done", "cancel"):
                continue
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
        order.invalidate_recordset()
        for picking in order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
        self.assertEqual(door.state, "delivered")
        self.assertEqual(self.Bundle.browse(b["id"]).state, "out")

    def test_lookup_reads_the_supply_order(self):
        partner = self.env["res.partner"].create({"name": "AA Impact"})
        product = self.env["product.product"].create({"name": "AA-1200 Hardware Kit (Black, 4 Panels)"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id, "client_order_ref": "W/O 1051 - BLAZE BLDRS",
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1})]})
        res = self.Bundle.board_lookup("1051")
        self.assertTrue(res["found"])
        self.assertEqual(res["order"], order.name)
        self.assertEqual(res["customer"], "BLAZE BLDRS")
        self.assertFalse(self.Bundle.board_lookup("105")["found"], "1051 is not order 105")
        self.assertFalse(self.Bundle.board_lookup("9999")["found"])
        b = self._receive([{"order_ref": "W/O 1051", "width": 107, "panels": 4}])
        door = self.Bundle.browse(b["id"]).door_ids
        self.assertEqual(door.order_ref, "1051")
        self.assertEqual(door.sale_order_id, order)

    def test_closed_spot_is_never_offered(self):
        level = self.env.ref("aa_door_racks.level_a1")
        self.Bundle.board_block({"level": level.id, "depth": "both", "arm_from": 0, "arm_to": 3,
                                 "note": "Glass crates"})
        for _i in range(3):
            spots = self.Bundle.board_suggest([{"width": 96, "panels": 4}])["spots"]
            self.assertNotIn(level.id, [s["level"] for s in spots])
        block = self.env["aa.rack.block"].search([])
        self.Bundle.board_unblock(block.id)
        spots = self.Bundle.board_suggest([{"width": 96, "panels": 4}])["spots"]
        self.assertIn(level.id, [s["level"] for s in spots[:12]] + [level.id])

    def test_close_a_whole_rack_by_clicking(self):
        """Every half of every row of rack B, clicked: one spot per level."""
        side = self.env.ref("aa_door_racks.level_b1").side_id
        clicked = [{"level": lv.id, "depth": depth, "arm_from": a, "arm_to": b}
                   for lv in side.level_ids.filtered("active") for depth in ("back", "front")
                   for a, b in ((0, 1), (2, 3))]
        self.assertEqual(self.Bundle.board_block_many(clicked, "Glass"), 5)
        blocks = self.env["aa.rack.block"].search([("side_id", "=", side.id)])
        self.assertEqual(set(blocks.mapped("depth")), {"both"})
        self.assertEqual({(b.arm_from, b.arm_to) for b in blocks}, {(0, 3)})
        self.assertEqual(set(blocks.mapped("note")), {"Glass"})
        spots = self.Bundle.board_suggest([{"width": 96, "panels": 4}])["spots"]
        self.assertNotIn(side.id, [s["side"] for s in spots])

    def test_close_many_keeps_rows_apart(self):
        b1 = self.env.ref("aa_door_racks.level_b1")
        self.Bundle.board_block_many([
            {"level": b1.id, "depth": "back", "arm_from": 0, "arm_to": 1},
            {"level": b1.id, "depth": "front", "arm_from": 2, "arm_to": 3},
        ])
        blocks = self.env["aa.rack.block"].search([("level_id", "=", b1.id)])
        self.assertEqual({(b.depth, b.arm_from, b.arm_to) for b in blocks},
                         {("back", 0, 1), ("front", 2, 3)})

    def test_close_many_refuses_a_spot_with_doors(self):
        b = self._receive([{"order_ref": "CM1", "width": 96, "panels": 4}])
        bundle = self.Bundle.browse(b["id"])
        other = self.env["aa.rack.level"].search([("id", "!=", bundle.level_id.id)], limit=1)
        with self.assertRaises(UserError):
            self.Bundle.board_block_many([
                {"level": other.id, "depth": "both", "arm_from": 0, "arm_to": 1},
                {"level": bundle.level_id.id, "depth": bundle.depth,
                 "arm_from": bundle.arm_from, "arm_to": bundle.arm_to},
            ])
