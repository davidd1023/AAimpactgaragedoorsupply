"""THE ADMIN AND THE OPERATORS' PINS.

Owner, 2026-10-28: *"as admin I should have the option to change Jorge's and
Michel's work-station PIN, and if I have the admin account I don't need to
type the PIN to get into their users, and I should be able to do on their work
stations the same as they do."*

TWO THINGS, BOTH FOR ADMINS ONLY (``base.group_system``, the same test the
Times tab uses):

* NO PIN FOR AN ADMIN. Signing in (or out) as an operator on the Shop Floor
  goes through ``hr.employee.login`` / ``logout``, which check the PIN. For an
  admin the employee's own PIN is handed in, so the check passes and Odoo
  carries on exactly as if it had been typed - the operator is signed in, his
  timers run under his name, and the admin can do at his station everything he
  can. ``pin_validation`` itself is NOT touched: the Attendance kiosk and
  anything else that asks for a PIN keeps asking.

  This only means something if the workers' devices are NOT signed in to Odoo
  as an admin. The owner, the same day: "admin will have his own device and
  michel and jorge another one each". If a worker's tablet were on an admin
  login, his PIN would be skipped for everybody standing at it.

* CHANGE PIN, from the Shop Floor's menu. The server refuses a non-admin,
  checks the PIN is digits, and never sends a PIN back - only whether one is
  set.
"""

from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError

#: Shortest PIN accepted from the Change PIN dialog.
PIN_MIN_LENGTH = 4


class HrEmployeeShopFloorPin(models.Model):
    _inherit = "hr.employee"

    # --- signing in without the PIN ----------------------------------------

    @api.model
    def aa_is_shop_floor_admin(self):
        return self.env.user.has_group("base.group_system")

    def _aa_shop_floor_pin(self, pin):
        """The PIN to check: the typed one, or for an admin the employee's own."""
        self.ensure_one()
        if self.aa_is_shop_floor_admin():
            return self.sudo().pin or False
        return pin

    @staticmethod
    def _aa_swap_pin(employee, args, kwargs):
        """Replace the ``pin`` argument, whether it came by position or name."""
        if "pin" in kwargs:
            kwargs["pin"] = employee._aa_shop_floor_pin(kwargs["pin"])
        elif args:
            args = (employee._aa_shop_floor_pin(args[0]),) + tuple(args[1:])
        else:
            kwargs["pin"] = employee._aa_shop_floor_pin(False)
        return args, kwargs

    def login(self, *args, **kwargs):
        if len(self) == 1:
            args, kwargs = self._aa_swap_pin(self, args, kwargs)
        return super().login(*args, **kwargs)

    def logout(self, *args, **kwargs):
        if len(self) == 1:
            args, kwargs = self._aa_swap_pin(self, args, kwargs)
        return super().logout(*args, **kwargs)

    # --- Change PIN ---------------------------------------------------------

    def _aa_check_shop_floor_admin(self):
        if not self.aa_is_shop_floor_admin():
            raise AccessError(_("Only an admin can change Shop Floor PINs."))

    @api.model
    def aa_shop_floor_pins(self):
        """The operators, and whether each has a PIN. Never the PIN itself."""
        self._aa_check_shop_floor_admin()
        employees = self.sudo().search(
            [("company_id", "in", self.env.companies.ids + [False])],
            order="name")
        return [
            {"id": employee.id, "name": employee.name, "has_pin": bool(employee.pin)}
            for employee in employees
        ]

    @api.model
    def aa_set_shop_floor_pin(self, employee_id, pin):
        self._aa_check_shop_floor_admin()
        pin = (pin or "").strip()
        if not pin.isdigit() or len(pin) < PIN_MIN_LENGTH:
            raise ValidationError(
                _("The PIN must be at least %s digits, numbers only.", PIN_MIN_LENGTH))

        employee = self.sudo().browse(int(employee_id)).exists()
        if not employee:
            raise ValidationError(_("That operator no longer exists."))

        employee.pin = pin
        return True
