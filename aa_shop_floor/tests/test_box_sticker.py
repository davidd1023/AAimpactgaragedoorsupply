"""FTSC and cable length the AA calculator's way (owner, 2026-11-27)."""

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.aa_shop_floor.models.box_sticker import aa_calculator_ftsc_cable


@tagged("post_install", "-at_install")
class CalculatorFormulaCase(TransactionCase):

    def test_a_seven_foot_door_matches_the_prepared_cable(self):
        # 7' 3" 15R on a D400-144: the prepared pair is 17.5 ft = 105" each.
        self.assertEqual(aa_calculator_ftsc_cable(84, "3-15R", "standard", 0, "D400-144"), (96.125, 105))

    def test_a_door_between_feet_is_worked_out_not_rounded_up(self):
        # 98" is not a 9' door: the table would say 129", the calculator 119".
        self.assertEqual(aa_calculator_ftsc_cable(98, "3-15R", "standard", 0, "D400-144"), (110.125, 119))

    def test_high_lift_takes_the_high_lift_off_the_cable(self):
        self.assertEqual(aa_calculator_ftsc_cable(96, "3-15R", "highlift", 24, "D525-54"), (123.125, 166))

    def test_what_the_calculator_does_not_know_stays_blank(self):
        self.assertEqual(aa_calculator_ftsc_cable(96, "2-15R", "standard", 0, "D400-96"), (None, None))
        self.assertEqual(aa_calculator_ftsc_cable(0, "3-15R", "standard", 0, "D400-96"), (None, None))
        self.assertEqual(aa_calculator_ftsc_cable(96, "3-15R", "highlift", 0, "D525-54"), (None, None))
