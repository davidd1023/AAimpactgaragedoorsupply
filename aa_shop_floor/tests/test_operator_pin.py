"""THE ADMIN AND THE OPERATORS' PINS (owner, 2026-10-28).

*"as admin I should have the option to change Jorge's and Michel's
work-station PIN, and if I have the admin account I don't need to type the
PIN to get into their users."*

What must hold: an admin passes the PIN check without typing anything, a
worker's login still has to type it, only an admin can change a PIN, and a
PIN is never handed back to the browser.
"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class OperatorPinCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.michel = self.env["hr.employee"].create({"name": "Michel", "pin": "1234"})
        self.admin = new_test_user(self.env, login="aa_pin_admin", groups="base.group_system")
        self.tablet = new_test_user(
            self.env, login="aa_pin_tablet", groups="base.group_user,mrp.group_mrp_user")

    def _as(self, user):
        return self.michel.with_user(user)

    # --- signing in --------------------------------------------------------

    def test_an_admin_needs_no_pin(self):
        employee = self._as(self.admin)
        pin = employee._aa_shop_floor_pin(False)
        self.assertTrue(employee.pin_validation(pin))

    def test_a_worker_tablet_still_needs_the_pin(self):
        employee = self._as(self.tablet)
        self.assertFalse(employee.pin_validation(employee._aa_shop_floor_pin(False)))
        self.assertFalse(employee.pin_validation(employee._aa_shop_floor_pin("9999")))
        self.assertTrue(employee.pin_validation(employee._aa_shop_floor_pin("1234")))

    def test_the_kiosk_check_itself_is_untouched(self):
        # pin_validation is not overridden: an admin calling it directly with
        # no PIN is still refused, so the Attendance kiosk keeps asking.
        self.assertFalse(self._as(self.admin).pin_validation(False))

    # --- Change PIN --------------------------------------------------------

    def test_an_admin_changes_a_pin(self):
        self.env["hr.employee"].with_user(self.admin).aa_set_shop_floor_pin(
            self.michel.id, "5678")
        self.assertEqual(self.michel.sudo().pin, "5678")

    def test_a_worker_cannot_change_a_pin(self):
        with self.assertRaises(AccessError):
            self.env["hr.employee"].with_user(self.tablet).aa_set_shop_floor_pin(
                self.michel.id, "5678")
        with self.assertRaises(AccessError):
            self.env["hr.employee"].with_user(self.tablet).aa_shop_floor_pins()
        self.assertEqual(self.michel.sudo().pin, "1234")

    def test_a_pin_must_be_four_digits(self):
        employees = self.env["hr.employee"].with_user(self.admin)
        for bad in ("", "12", "12a4", "abcd"):
            with self.assertRaises(ValidationError):
                employees.aa_set_shop_floor_pin(self.michel.id, bad)
        self.assertEqual(self.michel.sudo().pin, "1234")

    def test_the_list_never_carries_a_pin(self):
        rows = self.env["hr.employee"].with_user(self.admin).aa_shop_floor_pins()
        row = next(r for r in rows if r["id"] == self.michel.id)
        self.assertEqual(set(row), {"id", "name", "has_pin"})
        self.assertTrue(row["has_pin"])
