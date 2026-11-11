"""A SHOP FLOOR WORKER SEES ONLY THE SHOP FLOOR (owner, 2026-11-11)."""

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class ShopFloorOnlyCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.root = self.env.ref("mrp_workorder.menu_mrp_workorder_root")
        self.inventory = self.env.ref("stock.menu_stock_root")
        self.worker = new_test_user(
            self.env, login="aa_floor_only_worker",
            groups="base.group_user,mrp.group_mrp_user,aa_shop_floor.group_shop_floor_only")
        self.colleague = new_test_user(
            self.env, login="aa_floor_only_colleague",
            groups="base.group_user,mrp.group_mrp_user")
        self.admin = new_test_user(
            self.env, login="aa_floor_only_admin",
            groups="base.group_system,mrp.group_mrp_user,aa_shop_floor.group_shop_floor_only")

    def _visible(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def _shop_floor_tree(self):
        return set(self.env["ir.ui.menu"].search([("id", "child_of", self.root.id)])._ids)

    def test_the_worker_sees_the_shop_floor_and_nothing_else(self):
        visible = self._visible(self.worker)
        self.assertIn(self.root.id, visible, "the Shop Floor app must still be there")
        self.assertFalse(visible - self._shop_floor_tree(),
                         "every visible menu must belong to the Shop Floor")
        self.assertNotIn(self.inventory.id, visible)

    def test_his_rights_are_unchanged(self):
        """Only the menu is narrowed: the rights the Shop Floor needs stay."""
        self.assertTrue(self.worker.has_group("mrp.group_mrp_user"))
        self.assertTrue(self.worker.has_group("stock.group_stock_user"))

    def test_a_colleague_without_the_box_keeps_his_apps(self):
        visible = self._visible(self.colleague)
        self.assertIn(self.inventory.id, visible)
        self.assertIn(self.root.id, visible)

    def test_an_administrator_is_never_narrowed(self):
        self.assertIn(self.inventory.id, self._visible(self.admin))
