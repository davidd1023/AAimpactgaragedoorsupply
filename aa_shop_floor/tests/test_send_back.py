"""SEND A FINISHED JOB BACK TO ITS STATION (owner, 2026-11-11).

W/O 942's hardware was marked Done from an admin login with nothing packed.
An administrator can send it back: the stock is reversed and a fresh job takes
its place on the station.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class SendBackCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.stock = self.env.ref("stock.warehouse0").lot_stock_id
        self.part = self.env["product.product"].create({
            "name": "Send Back Test Part", "type": "consu", "is_storable": True})
        self.made = self.env["product.product"].create({
            "name": "Send Back Test Kit", "type": "consu", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(self.part, self.stock, 10)
        self.order = self.env["sale.order"].create({
            "partner_id": self.env["res.partner"].create({"name": "Send Back Dealer"}).id})
        self.admin = self.env.ref("base.user_admin")

    def _done_job(self):
        job = self.env["mrp.production"].create({
            "product_id": self.made.id,
            "product_qty": 2.0,
            "origin": self.order.name,
            "move_raw_ids": [(0, 0, {"product_id": self.part.id, "product_uom_qty": 3.0})],
        })
        job.action_confirm()
        job.action_assign()
        job.qty_producing = 2.0
        job.move_raw_ids.picked = True
        job.button_mark_done()
        self.assertEqual(job.state, "done")
        return job

    def test_the_stock_is_put_back_and_a_fresh_job_replaces_it(self):
        job = self._done_job()
        self.assertEqual(self.part.qty_available, 7.0)
        self.assertEqual(self.made.qty_available, 2.0)

        new_ids = job.with_user(self.admin).aa_send_back()

        self.assertTrue(job.aa_sent_back)
        self.assertEqual(self.part.qty_available, 10.0, "what it used is back on the shelf")
        self.assertEqual(self.made.qty_available, 0.0, "what it made is off the shelf")
        new = self.env["mrp.production"].browse(new_ids)
        self.assertEqual(len(new), 1)
        self.assertNotIn(new.state, ("done", "cancel"))
        self.assertEqual(new.origin, self.order.name)
        self.assertEqual(new.product_qty, 2.0)
        self.assertEqual(new.move_raw_ids.product_id, self.part)
        self.assertIn("marked done by", job.message_ids[0].body)

    def test_the_order_sees_one_job_and_it_is_not_done(self):
        job = self._done_job()
        new = self.env["mrp.production"].browse(job.with_user(self.admin).aa_send_back())
        siblings = new._aa_order_siblings()
        self.assertIn(new, siblings)
        self.assertNotIn(job, siblings)

    def test_only_an_administrator_can_send_back(self):
        job = self._done_job()
        manager = new_test_user(self.env, login="aa_send_back_manager",
                                groups="base.group_user,mrp.group_mrp_manager")
        with self.assertRaises(AccessError):
            job.with_user(manager).aa_send_back()
        self.assertFalse(job.aa_sent_back)

    def test_an_unfinished_or_already_sent_back_job_is_refused(self):
        job = self._done_job()
        job.with_user(self.admin).aa_send_back()
        with self.assertRaises(UserError):
            job.with_user(self.admin).aa_send_back()
        open_job = self.env["mrp.production"].create({
            "product_id": self.made.id, "product_qty": 1.0, "origin": self.order.name})
        open_job.action_confirm()
        with self.assertRaises(UserError):
            open_job.with_user(self.admin).aa_send_back()
