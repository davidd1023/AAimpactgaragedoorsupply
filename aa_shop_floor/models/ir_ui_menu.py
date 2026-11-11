"""ONLY THE SHOP FLOOR IN THE MENU FOR A SHOP FLOOR WORKER (owner, 2026-11-11).

"a jorge y a michel cuando entren con sus usuarios quiero que solo vean
shopfloor" - Jorge and Michel, signed in as themselves, should see the Shop
Floor and nothing else.

RIGHTS CANNOT DO IT. The Shop Floor needs Manufacturing and Inventory rights
to work, and Odoo shows every app whose rights a user holds, so the Inventory
and Manufacturing apps came with the job. Editing Odoo's own menus by hand
would hide them from everybody else as well, and the next update of `stock`
or `mrp` would put them back.

SO A GROUP NARROWS THE MENU AND NOTHING ELSE. `_visible_menu_ids` is cached
per set of groups the user holds, which is exactly the key this needs: a member
of `group_shop_floor_only` has a different set from everybody else and gets
his own cached answer. No right changes - a member can open whatever he could
before by its address; he is just not shown it. An administrator is never
narrowed, even if somebody ticks the box on him.
"""

from odoo import models

SHOP_FLOOR_ONLY = "aa_shop_floor.group_shop_floor_only"
SHOP_FLOOR_ROOT = "mrp_workorder.menu_mrp_workorder_root"


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug)
        user = self.env.user
        if not user.has_group(SHOP_FLOOR_ONLY) or user.has_group("base.group_system"):
            return visible
        root = self.env.ref(SHOP_FLOOR_ROOT, raise_if_not_found=False)
        if not root:
            # No Shop Floor app to narrow to: hiding everything would leave a
            # worker with an empty screen, which is worse than the full menu.
            return visible
        shop_floor = set(self.sudo().with_context(active_test=False).search(
            [("id", "child_of", root.id)])._ids)
        return frozenset(visible & shop_floor)
