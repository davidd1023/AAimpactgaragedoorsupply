"""Work the spring stock straight from Floor / Rack / Boxes (owner, 2026-10-20).

The owner wants one page for the spring stock: move coils from a box down to the
floor there, and fix the counts there when springs were used without the system
knowing - on the Floor, the Rack or in a Box. With that, the separate Spring
Boxes menu is no longer needed.

* Move to Floor (Boxes rows): the box's move wizard, showing only that row's
  wire and I.D.
* Adjust (every row): one line per piece (lot) of that wire and I.D. in that
  place. Change a piece's inches, set it to 0 to take it out, or add a new
  piece. Applied as an ordinary inventory adjustment, so it shows in the moves
  history.
* Add Coils (top of the page): coils into a new box or one already in stock.
* A box is closed by itself once it is empty.
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coil import FULL_COIL, ID_CODES, ID_LABELS

HAND_SELECTION = [("L", "LH"), ("R", "RH")]


def _place_location(env, name):
    """AAM/Stock/<name> (Floor or Rack), created if missing."""
    warehouse = env["stock.warehouse"].sudo().search([("company_id", "=", env.company.id)], limit=1)
    Location = env["stock.location"].sudo()
    location = Location.search([("name", "=", name), ("usage", "=", "internal"),
                                ("location_id", "=", warehouse.lot_stock_id.id)], limit=1)
    return location or Location.create({"name": name, "usage": "internal",
                                        "location_id": warehouse.lot_stock_id.id})


class AaSpringPlaceSummary(models.Model):
    _inherit = "aa.spring.place.summary"

    def _row_id_code(self):
        self.ensure_one()
        return ID_CODES.get(round(self.inside_diameter_num or 0.0, 4))

    def _row_location(self):
        """The location this row's pieces sit in (the box's own location for Boxes)."""
        self.ensure_one()
        if self.place == "Boxes":
            if not self.box_id or not self.box_id.location_id:
                raise UserError(_("This line is not in a numbered box."))
            return self.box_id.location_id
        return _place_location(self.env, self.place)

    def _row_codes(self):
        self.ensure_one()
        id_code = self._row_id_code()
        if not id_code or not self.wire:
            raise UserError(_("Unknown wire or I.D. on this line."))
        return ["COIL-%s-%s-%s" % (self.wire, id_code, hand) for hand in ("L", "R")]

    def action_adjust(self):
        self.ensure_one()
        location = self._row_location()
        wizard = self.env["aa.spring.adjust"].create({
            "place": self.place,
            "box_id": self.box_id.id if self.place == "Boxes" else False,
            "location_id": location.id,
            "wire": self.wire,
            "id_code": self._row_id_code(),
        })
        wizard._fill_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Adjust %(place)s: %(id)s .%(wire)s", place=self.box_id.name if self.place == "Boxes"
                      else self.place, id=self.inside_diameter, wire=self.wire),
            "res_model": "aa.spring.adjust",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_move_to_floor(self):
        self.ensure_one()
        if self.place != "Boxes" or not self.box_id:
            raise UserError(_("Only coils in a box can be moved to the floor."))
        wizard = self.env["aa.spring.box.move"].create({"box_id": self.box_id.id})
        wizard._fill_lines(codes=self._row_codes())
        if not wizard.line_ids:
            raise UserError(_("Every coil of this size in %s is already reserved for an order.",
                              self.box_id.name))
        return {
            "type": "ir.actions.act_window",
            "name": _("Move from %(box)s to the Floor: %(id)s .%(wire)s", box=self.box_id.name,
                      id=self.inside_diameter, wire=self.wire),
            "res_model": "aa.spring.box.move",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_add_coils(self):
        """Top-of-page button: coils into a new box (or one already in stock).

        Not @api.model: a list header button sends the (empty) selection as ids."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Add Coils to a Box"),
            "res_model": "aa.spring.box.add",
            "view_mode": "form",
            "target": "new",
        }


class AaSpringAdjust(models.TransientModel):
    _name = "aa.spring.adjust"
    _description = "Adjust Spring Coil Pieces"

    place = fields.Char(readonly=True)
    box_id = fields.Many2one("aa.spring.box", readonly=True)
    location_id = fields.Many2one("stock.location", required=True, readonly=True)
    wire = fields.Char(readonly=True)
    id_code = fields.Char(readonly=True)
    inside_diameter = fields.Char(string="I.D.", compute="_compute_label")
    reason = fields.Char(string="Reason", help="Shown in the inventory moves history.")
    line_ids = fields.One2many("aa.spring.adjust.line", "wizard_id", string="Pieces")

    @api.depends("id_code")
    def _compute_label(self):
        for wizard in self:
            wizard.inside_diameter = ID_LABELS.get(wizard.id_code, wizard.id_code)

    def _quants(self):
        self.ensure_one()
        codes = ["COIL-%s-%s-%s" % (self.wire, self.id_code, hand) for hand in ("L", "R")]
        return self.env["stock.quant"].sudo().search([
            ("location_id", "=", self.location_id.id),
            ("product_id.default_code", "in", codes),
            ("quantity", ">", 0.001),
        ])

    def _fill_lines(self):
        self.ensure_one()
        quants = self._quants().sorted(
            lambda q: (q.product_id.default_code[-1], q.lot_id.name or ""))
        self.line_ids = [(0, 0, {
            "quant_id": quant.id,
            "hand": quant.product_id.default_code[-1],
            "current": quant.quantity,
            "reserved": quant.reserved_quantity,
            "new_qty": quant.quantity,
        }) for quant in quants]

    def _new_lot_name(self, product):
        """A name for a piece added by hand, following its place's pattern."""
        if self.box_id:
            return self.box_id._next_lot_names(product, 1)[0]
        prefix = "%s-%s-" % (self.wire, self.id_code)
        suffix = "-%s" % product.default_code[-1]
        names = self.env["stock.lot"].sudo().search([
            ("product_id", "=", product.id), ("name", "=like", prefix + "%")]).mapped("name")
        pattern = re.compile(re.escape(prefix) + r"(\d+)" + re.escape(suffix) + "$")
        used = [int(m.group(1)) for m in map(pattern.match, names) if m]
        return "%s%s%s" % (prefix, max(used, default=0) + 1, suffix)

    def action_apply(self):
        self.ensure_one()
        from .spring_box import _coil_product

        Quant = self.env["stock.quant"].sudo().with_context(inventory_mode=True)
        Lot = self.env["stock.lot"].sudo()
        to_apply = Quant
        for line in self.line_ids:
            if line.new_qty < 0:
                raise ValidationError(_("A piece cannot be shorter than 0\"."))
            if line.quant_id:
                quant = line.quant_id.sudo().with_context(inventory_mode=True)
                if abs(line.new_qty - quant.quantity) < 0.001:
                    continue
                if line.new_qty < quant.reserved_quantity - 0.001:
                    raise UserError(_(
                        "%(lot)s is reserved for an order (%(res)s\"). Finish or cancel that order "
                        "before taking it below %(res)s\".",
                        lot=quant.lot_id.name, res="%g" % quant.reserved_quantity))
                quant.inventory_quantity = line.new_qty
                to_apply |= quant
            elif line.new_qty > 0.001:
                if not line.hand:
                    raise UserError(_("Choose LH or RH for every new piece."))
                product = _coil_product(self.env, self.wire, self.id_code, line.hand)
                lot = Lot.create({"name": self._new_lot_name(product), "product_id": product.id,
                                  "company_id": self.env.company.id})
                to_apply |= Quant.create({
                    "product_id": product.id,
                    "location_id": self.location_id.id,
                    "lot_id": lot.id,
                    "inventory_quantity": line.new_qty,
                })
        if not to_apply:
            raise UserError(_("Nothing was changed."))
        where = self.box_id.name if self.box_id else self.place
        name = _("Spring adjustment (%s)", where)
        if self.reason:
            name = "%s: %s" % (name, self.reason)
        to_apply.with_context(inventory_name=name).action_apply_inventory()
        if self.box_id:
            self.box_id._aa_close_if_empty()
        return {"type": "ir.actions.act_window_close"}


class AaSpringAdjustLine(models.TransientModel):
    _name = "aa.spring.adjust.line"
    _description = "Spring Coil Piece to Adjust"

    wizard_id = fields.Many2one("aa.spring.adjust", required=True, ondelete="cascade")
    quant_id = fields.Many2one("stock.quant", readonly=True)
    lot_id = fields.Many2one(related="quant_id.lot_id", string="Piece")
    hand = fields.Selection(HAND_SELECTION, string="Hand")
    current = fields.Float(string="On Hand (in)", readonly=True, digits=(16, 2))
    reserved = fields.Float(string="Reserved (in)", readonly=True, digits=(16, 2))
    new_qty = fields.Float(string="Real (in)", digits=(16, 2),
                           default=FULL_COIL, help="0 takes the piece out of stock.")
    is_new = fields.Boolean(compute="_compute_is_new")

    @api.depends("quant_id")
    def _compute_is_new(self):
        for line in self:
            line.is_new = not line.quant_id
