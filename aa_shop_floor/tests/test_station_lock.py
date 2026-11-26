"""EACH WORKER SEES ONLY HIS OWN STATIONS (owner, 2026-11-26)."""

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class StationLockCase(TransactionCase):

    def setUp(self):
        super().setUp()
        groups = "base.group_user,mrp.group_mrp_user,aa_shop_floor.group_shop_floor_only"
        self.jorge = new_test_user(self.env, login="aa_lock_jorge", groups=groups)
        self.michel = new_test_user(self.env, login="aa_lock_michel", groups=groups)
        self.lonely = new_test_user(self.env, login="aa_lock_lonely", groups=groups)
        self.admin = new_test_user(
            self.env, login="aa_lock_admin",
            groups="base.group_system,mrp.group_mrp_user,aa_shop_floor.group_shop_floor_only")
        self.colleague = new_test_user(
            self.env, login="aa_lock_colleague", groups="base.group_user,mrp.group_mrp_user")
        Employee = self.env["hr.employee"]
        jorge = Employee.create({"name": "Jorge (lock)", "user_id": self.jorge.id})
        michel = Employee.create({"name": "Michel (lock)", "user_id": self.michel.id})
        admin = Employee.create({"name": "Admin (lock)", "user_id": self.admin.id})
        Employee.create({"name": "Lonely (lock)", "user_id": self.lonely.id})
        Center = self.env["mrp.workcenter"]
        self.tracks = Center.create({"name": "Lock Track Prep", "sequence": 1,
                                     "employee_ids": [(6, 0, (jorge | admin).ids)]})
        self.hardware = Center.create({"name": "Lock Hardware", "sequence": 2,
                                       "employee_ids": [(6, 0, michel.ids)]})
        self.springs = Center.create({"name": "Lock Springs", "sequence": 3,
                                      "employee_ids": [(6, 0, michel.ids)]})
        self.pending = Center.create({"name": "Lock Pending", "sequence": 0})

    def _ids(self, user):
        stations = user._aa_shop_floor_stations()
        return [wc["id"] for wc in stations] if stations else stations

    def test_jorge_gets_track_prep_only(self):
        self.assertEqual(self._ids(self.jorge), [self.tracks.id])

    def test_michel_gets_hardware_and_springs_in_order(self):
        self.assertEqual(self._ids(self.michel), [self.hardware.id, self.springs.id])

    def test_the_admin_is_never_locked(self):
        self.assertFalse(self._ids(self.admin))

    def test_a_colleague_without_the_box_is_not_locked(self):
        self.assertFalse(self._ids(self.colleague))

    def test_a_worker_with_no_station_keeps_the_normal_shop_floor(self):
        self.assertFalse(self._ids(self.lonely))

    def test_the_list_reaches_the_browser(self):
        info = self.env["ir.http"].with_user(self.michel).session_info()
        self.assertEqual([wc["id"] for wc in info["aa_shop_floor_stations"]],
                         [self.hardware.id, self.springs.id])
        self.assertEqual(info["aa_shop_floor_stations"][0]["display_name"], "Lock Hardware")
