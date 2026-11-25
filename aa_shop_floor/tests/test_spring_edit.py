"""ADMIN: CHANGE A SPRING BEFORE IT IS WOUND (owner, 2026-11-25)."""
import json

from odoo.addons.website.tools import MockRequest
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


def spec(spring_id=2.625, wire=0.2625, length=30.0, drum="CANIMEX/TF D400-96", hi_lift=0):
    return {
        "assembly": "Single",
        "springs": 2,
        "drum": drum,
        "turns": 7.5,
        "cycles": "10,000",
        "doorWeight": "180",
        "doorHeight": "7' 0\"",
        "doorWidth": "9' 0\"",
        "hiLift": hi_lift,
        "springsSpec": [{"role": "Spring", "wire": wire, "id": spring_id, "length": length}],
    }


@tagged("post_install", "-at_install")
class SpringEditCase(TransactionCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.spring_engineering.controllers.main import quote_assembly
        self.quote_assembly = quote_assembly
        self.partner = self.env["res.partner"].create({"name": "Spring Edit Dealer"})
        self.spring = self.env.ref("spring_engineering.product_custom_spring").product_variant_id
        self.filler = self.env.ref("spring_engineering.product_custom_filler").product_variant_id
        self.order = self.env["sale.order"].create({"partner_id": self.partner.id})
        with MockRequest(self.env):
            quote = self.quote_assembly(spec())
        self.line = self.env["sale.order.line"].create({
            "order_id": self.order.id,
            "product_id": self.spring.id,
            "product_uom_qty": 1,
            "name": quote["description"],
            "aa_spec_note": "\n".join(quote["description"].splitlines()[1:]),
            "price_unit": quote["assembly_total"],
            "spring_spec_json": json.dumps(quote["spec"]),
        })
        self.line.aa_write_door(quote["door"])
        self.order.action_confirm()
        self.job = self.line._aa_spring_jobs()

    def _respec(self, new, user=None):
        line = self.line.with_user(user) if user else self.line
        with MockRequest(self.env):
            return line.aa_respec_spring(new)

    def test_the_order_and_the_job_take_the_new_spring(self):
        self.assertTrue(self.job, "confirming made no Springs job")
        old_price = self.line.price_subtotal
        result = self._respec(spec(wire=0.273, length=34.0, drum="CANIMEX/TF D400-144"))
        stored = json.loads(self.line.spring_spec_json)
        self.assertEqual(stored["items"][0]["wire"], 0.273)
        self.assertEqual(stored["items"][0]["length"], 34.0)
        self.assertEqual(stored["drum"], "CANIMEX/TF D400-144")
        self.assertIn('0.273" wire', self.line.name)
        self.assertNotEqual(self.line.price_subtotal, old_price)
        self.assertEqual(result["new_total"], round(self.line.price_subtotal, 2))
        self.assertEqual(json.loads(self.job.aa_spring_spec_json)["items"][0]["length"], 34.0,
                         "Michel's job must wind the new spring")

    def test_a_five_and_a_quarter_brings_its_filler_and_takes_it_away(self):
        self._respec(spec(spring_id=5.25, wire=0.3125, length=36.0))
        filler = self.order.order_line.filtered(lambda l: l.product_id == self.filler and l.product_uom_qty)
        self.assertEqual(filler.product_uom_qty, 6.0, "two springs of 36\" = 6 ft of filler")
        self._respec(spec())
        self.assertFalse(self.order.order_line.filtered(
            lambda l: l.product_id == self.filler and l.product_uom_qty))

    def test_hi_lift_is_written_on_the_door(self):
        self._respec(spec(drum="CANIMEX/TF D800-120", hi_lift=36))
        self.assertEqual(self.line.aa_door_hi_lift_in, 36)
        self.assertIn('36" hi-lift', self.line.name)

    def test_only_an_admin(self):
        clerk = self.env["res.users"].create({
            "name": "Spring Clerk", "login": "spring_edit_clerk",
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id,
                                  self.env.ref("mrp.group_mrp_user").id])],
        })
        with self.assertRaises(UserError):
            self._respec(spec(wire=0.273), user=clerk)

    def test_refused_once_the_springs_are_done(self):
        self.job.write({"state": "done"})
        self.assertTrue(self.line._aa_spring_edit_refusal())
        with self.assertRaises(UserError):
            self._respec(spec(wire=0.273))

    def test_the_board_offers_it_to_an_admin(self):
        rows = self.order._aa_spring_edit_board()
        self.assertEqual(rows[0]["line_id"], self.line.id)
        self.assertEqual(rows[0]["start"]["spring_id"], '2 5/8"')
        self.assertFalse(rows[0]["locked"])
