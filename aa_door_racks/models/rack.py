from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from . import engine


class AaRackSide(models.Model):
    """One side of a cantilever rack - A, B, C, D or E."""
    _name = "aa.rack.side"
    _description = "Door Rack Side"
    _order = "sequence, name"

    name = fields.Char(required=True, help="The letter the shop uses: A, B, C...")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    arm_positions = fields.Char(
        required=True, default="0, 74.5, 134.5, 209",
        help="Where the arms are along the side, in inches from the first one.")
    overhang = fields.Float(
        default=24.0, help="How far a door may stick out past the outer arms, in inches.")
    arm_length = fields.Float(default=53.0, help="Arm length (depth), in inches.")
    allow_fallback = fields.Boolean(
        string="11' Doors on One Unit", default=True,
        help="A door over 10' that cannot reach three arms may rest on the widest pair of arms.")
    level_ids = fields.One2many("aa.rack.level", "side_id", string="Levels")

    _name_uniq = models.Constraint("unique(name)", "Each rack side needs its own letter.")

    @api.constrains("arm_positions")
    def _check_arms(self):
        for side in self:
            try:
                arms = side._arms()
            except ValueError:
                raise ValidationError(_("Arm positions must be numbers separated by commas."))
            if len(arms) < 2 or arms != sorted(arms):
                raise ValidationError(_("Give at least two arm positions, smallest first."))

    def _arms(self):
        self.ensure_one()
        return [float(x) for x in (self.arm_positions or "").replace(";", ",").split(",") if x.strip()]

    def _spec(self):
        self.ensure_one()
        levels = self.level_ids.filtered("active")
        return engine.SideSpec(
            key=self.id, arms=self._arms(), overhang=self.overhang,
            allow_fallback=self.allow_fallback,
            levels={lv.id: lv.clearance for lv in levels},
            level_numbers={lv.id: lv.number for lv in levels})


class AaRackLevel(models.Model):
    _name = "aa.rack.level"
    _description = "Door Rack Level"
    _order = "side_id, number"
    _rec_name = "code"

    side_id = fields.Many2one("aa.rack.side", required=True, ondelete="cascade")
    number = fields.Integer(required=True, help="Counted from the floor up: 1 is the floor legs.")
    clearance = fields.Float(
        string="Clear Height (in)",
        help="Usable height on this level, in inches. 0 means no limit (the top level).")
    active = fields.Boolean(default=True)
    code = fields.Char(compute="_compute_code", store=True)

    _side_number_uniq = models.Constraint(
        "unique(side_id, number)", "A side cannot have the same level twice.")

    @api.depends("side_id.name", "number")
    def _compute_code(self):
        for level in self:
            level.code = "%s%s" % (level.side_id.name or "", level.number or "")
