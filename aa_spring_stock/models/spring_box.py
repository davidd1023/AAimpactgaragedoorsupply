"""Numbered boxes of spring coils.

Springs come from the supplier in big boxes, and AA keeps them in those boxes
until there is room on the floor (owner, 2026-10-19). Each box is a location
under AAM/Stock/Boxes ("Box 3"), so its coils are ordinary stock: the summary
counts them as Boxes and a Springs order takes from them last.

* Add coils: wire, I.D. and how many LH / RH coils - one box can hold several
  sizes. Each coil becomes its own lot (BOX3-262-2.625-L-01), 84" long.
* Move to Floor: pick how many coils of each line go down to the floor.
* Remove Box: only when it is empty (owner, 2026-10-19).
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coil import FULL_COIL, ID_LABELS, WIRE_CODES

WIRE_SELECTION = [(code, ".%s" % code) for code in sorted(WIRE_CODES)]
ID_SELECTION = [(code, label) for code, label in ID_LABELS.items()]
HAND_SELECTION = [("L", "LH"), ("R", "RH")]


def _coil_product(env, wire, id_code, hand):
    """The coil product COIL-<wire>-<I.D.>-<hand>, created like its siblings if missing."""
    Product = env["product.product"].sudo().with_context(active_test=False)
    code = "COIL-%s-%s-%s" % (wire, id_code, hand)
    product = Product.search([("default_code", "=", code)], limit=1)
    if product:
        if not product.active:
            product.active = True
        return product
    sibling = Product.search([("default_code", "=like", "COIL-%")], limit=1)
    if not sibling:
        raise UserError(_("There is no spring coil product to copy from. Create %s first.", code))
    twin = Product.search([("default_code", "=like", "COIL-%s-%s-%%" % (wire, id_code))], limit=1)
    label = ID_LABELS.get(id_code, id_code)
    return sibling.copy({
        "name": 'Torsion Spring Coil %s I.D. x %g" (.%s, %s)' % (label, FULL_COIL, wire, hand),
        "default_code": code,
        "standard_price": (twin or sibling).standard_price if twin else 0.0,
        "active": True,
    })


class AaSpringBox(models.Model):
    _name = "aa.spring.box"
    _description = "Spring Coil Box"
    _order = "state, number"
    _rec_name = "name"

    number = fields.Integer(string="Box #", required=True, index=True,
                            default=lambda self: self._next_number())
    name = fields.Char(compute="_compute_name", store=True)
    state = fields.Selection([("open", "In Stock"), ("closed", "Removed")], default="open",
                             required=True, index=True)
    location_id = fields.Many2one("stock.location", string="Location", readonly=True, copy=False,
                                  ondelete="restrict")
    date = fields.Date(string="Received", default=fields.Date.context_today)
    note = fields.Char()
    content_ids = fields.One2many("aa.spring.place.summary", "box_id", string="Contents", readonly=True)
    l_coils = fields.Integer(string="LH Coils", compute="_compute_coils")
    r_coils = fields.Integer(string="RH Coils", compute="_compute_coils")
    is_empty = fields.Boolean(compute="_compute_coils")
    contents_label = fields.Char(string="What's Inside", compute="_compute_coils")

    @api.depends("number")
    def _compute_name(self):
        for box in self:
            box.name = _("Box %s", box.number)

    def _quants(self):
        return self.env["stock.quant"].sudo().search([
            ("location_id", "in", self.location_id.ids),
            ("product_id.default_code", "=like", "COIL-%"),
            ("quantity", ">", 0.001),
        ])

    def _compute_coils(self):
        for box in self:
            quants = box._quants() if box.location_id else self.env["stock.quant"]
            box.l_coils = len(quants.filtered(lambda q: q.product_id.default_code.endswith("-L")))
            box.r_coils = len(quants.filtered(lambda q: q.product_id.default_code.endswith("-R")))
            box.is_empty = not quants
            rows = {}
            for quant in quants:
                _c, wire, id_code, hand = quant.product_id.default_code.split("-")
                row = rows.setdefault((id_code, wire), {"L": 0, "R": 0})
                row[hand] += 1
            box.contents_label = " · ".join(
                "%s .%s: %s" % (ID_LABELS.get(id_code, id_code), wire,
                                " ".join("%s %sH" % (n, h) for h, n in counts.items() if n))
                for (id_code, wire), counts in sorted(
                    rows.items(), key=lambda kv: (float(kv[0][0]), kv[0][1])))

    @api.model
    def _next_number(self):
        open_numbers = set(self.search([("state", "=", "open")]).mapped("number"))
        number = 1
        while number in open_numbers:
            number += 1
        return number

    @api.constrains("number", "state")
    def _check_number(self):
        for box in self:
            if box.number <= 0:
                raise ValidationError(_("The box number must be 1 or more."))
            if box.state == "open" and self.search_count([
                    ("number", "=", box.number), ("state", "=", "open"), ("id", "!=", box.id)]):
                raise ValidationError(_("There is already a Box %s in stock.", box.number))

    @api.model
    def _boxes_location(self):
        warehouse = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", self.env.company.id)], limit=1)
        Location = self.env["stock.location"].sudo()
        boxes = Location.search([("name", "=", "Boxes"), ("usage", "=", "internal"),
                                 ("location_id", "=", warehouse.lot_stock_id.id)], limit=1)
        return boxes or Location.create({"name": "Boxes", "usage": "internal",
                                         "location_id": warehouse.lot_stock_id.id})

    @api.model
    def _floor_location(self):
        warehouse = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", self.env.company.id)], limit=1)
        Location = self.env["stock.location"].sudo()
        floor = Location.search([("name", "=", "Floor"), ("usage", "=", "internal"),
                                 ("location_id", "=", warehouse.lot_stock_id.id)], limit=1)
        return floor or Location.create({"name": "Floor", "usage": "internal",
                                         "location_id": warehouse.lot_stock_id.id})

    def _ensure_location(self):
        Location = self.env["stock.location"].sudo().with_context(active_test=False)
        parent = self._boxes_location()
        for box in self:
            name = "Box %s" % box.number
            if box.location_id:
                if box.location_id.name != name or not box.location_id.active:
                    box.location_id.write({"name": name, "active": True})
                continue
            location = Location.search([("name", "=", name), ("location_id", "=", parent.id)], limit=1)
            if location and self.search_count([("location_id", "=", location.id), ("state", "=", "open")]):
                location = False
            if location:
                location.active = True
            else:
                location = Location.create({"name": name, "usage": "internal", "location_id": parent.id})
            box.location_id = location

    @api.model_create_multi
    def create(self, vals_list):
        boxes = super().create(vals_list)
        boxes._ensure_location()
        return boxes

    def write(self, vals):
        result = super().write(vals)
        if "number" in vals:
            self.filtered(lambda b: b.state == "open")._ensure_location()
        return result

    def unlink(self):
        for box in self:
            if box.location_id and box._quants():
                raise UserError(_("%s still has coils. Move them to the floor first.", box.name))
        locations = self.location_id
        result = super().unlink()
        locations.sudo().write({"active": False})
        return result

    # --- buttons ---------------------------------------------------------------------

    def action_add_coils(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Add Coils to %s", self.name),
            "res_model": "aa.spring.box.add",
            "view_mode": "form",
            "target": "new",
            "context": {"default_box_id": self.id},
        }

    def action_move_to_floor(self):
        self.ensure_one()
        if self.is_empty:
            raise UserError(_("%s is empty.", self.name))
        wizard = self.env["aa.spring.box.move"].create({"box_id": self.id})
        wizard._fill_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Move Coils from %s to the Floor", self.name),
            "res_model": "aa.spring.box.move",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_remove(self):
        for box in self:
            if box._quants():
                raise UserError(_("%s still has coils. Move them to the floor first - a box is "
                                  "only removed when it is empty.", box.name))
            box.state = "closed"
            box.location_id.sudo().active = False
        return True

    def _aa_close_if_empty(self):
        """A box is removed by itself once its last coil is gone (owner, 2026-10-20)."""
        for box in self.filtered(lambda b: b.state == "open" and b.location_id):
            if not box._quants():
                box.state = "closed"
                box.location_id.sudo().active = False
        return True

    def action_view_coils(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("aa_spring_stock.action_aa_coil_pieces")
        action["domain"] = [("location_id", "=", self.location_id.id), ("quantity", ">", 0)]
        action["context"] = {"search_default_group_product": 1}
        action["name"] = self.name
        return action

    # --- putting coils in --------------------------------------------------------------

    def _next_lot_names(self, product, count):
        """count new lot names BOX<n>-<wire>-<I.D.>-<hand>-NN for this product."""
        self.ensure_one()
        prefix = "BOX%s-%s-" % (self.number, product.default_code[len("COIL-"):])
        names = self.env["stock.lot"].sudo().search([
            ("product_id", "=", product.id), ("name", "=like", prefix + "%")]).mapped("name")
        used = [int(m.group(1)) for m in (re.match(re.escape(prefix) + r"(\d+)$", n) for n in names) if m]
        start = max(used, default=0) + 1
        return ["%s%02d" % (prefix, n) for n in range(start, start + count)]

    def _put_coils(self, product, count, length=FULL_COIL):
        """Add `count` coils of `product` to this box, each its own lot."""
        self.ensure_one()
        if count <= 0:
            return
        if self.state != "open":
            raise UserError(_("%s has been removed.", self.name))
        self._ensure_location()
        Lot = self.env["stock.lot"].sudo()
        Quant = self.env["stock.quant"].sudo().with_context(inventory_mode=True)
        quants = Quant
        for name in self._next_lot_names(product, count):
            lot = Lot.create({"name": name, "product_id": product.id, "company_id": self.env.company.id})
            quants |= Quant.create({
                "product_id": product.id,
                "location_id": self.location_id.id,
                "lot_id": lot.id,
                "inventory_quantity": length,
            })
        quants.with_context(inventory_name=_("%s received", self.name)).action_apply_inventory()

    @api.model
    def _aa_adopt_loose_box_coils(self):
        """Coils sitting straight in Boxes with a BOX<n>- lot go into their numbered box."""
        parent = self._boxes_location()
        quants = self.env["stock.quant"].sudo().search([
            ("location_id", "=", parent.id), ("quantity", ">", 0.001),
            ("product_id.default_code", "=like", "COIL-%")])
        by_box = {}
        for quant in quants:
            match = re.match(r"BOX(\d+)-", quant.lot_id.name or "")
            if match and not quant.reserved_quantity:
                by_box.setdefault(int(match.group(1)), self.env["stock.quant"].sudo())
                by_box[int(match.group(1))] |= quant
        for number, box_quants in by_box.items():
            box = self.search([("number", "=", number), ("state", "=", "open")], limit=1) \
                or self.create({"number": number})
            box_quants.move_quants(location_dest_id=box.location_id,
                                   message=_("Put in %s", box.name))
        return True


class AaSpringBoxAdd(models.TransientModel):
    _name = "aa.spring.box.add"
    _description = "Add Coils to a Box"

    box_id = fields.Many2one("aa.spring.box", string="Box", ondelete="cascade",
                             domain=[("state", "=", "open")],
                             help="Leave empty to start a new box.")
    new_box_number = fields.Integer(string="New Box #",
                                    default=lambda self: self.env["aa.spring.box"]._next_number())
    line_ids = fields.One2many("aa.spring.box.add.line", "wizard_id", string="Coils")

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.l_qty > 0 or l.r_qty > 0)
        if not lines:
            raise UserError(_("Enter at least one line with LH or RH coils."))
        if not self.box_id:
            if self.new_box_number <= 0:
                raise UserError(_("Enter the number of the new box."))
            self.box_id = self.env["aa.spring.box"].create({"number": self.new_box_number})
        for line in lines:
            for hand, qty in (("L", line.l_qty), ("R", line.r_qty)):
                if qty > 0:
                    product = _coil_product(self.env, line.wire, line.inside_diameter, hand)
                    self.box_id._put_coils(product, qty, line.length or FULL_COIL)
        return {"type": "ir.actions.act_window_close"}


class AaSpringBoxAddLine(models.TransientModel):
    _name = "aa.spring.box.add.line"
    _description = "Coils to Add to a Box"

    wizard_id = fields.Many2one("aa.spring.box.add", required=True, ondelete="cascade")
    inside_diameter = fields.Selection(ID_SELECTION, string="I.D.", required=True, default="2.625")
    wire = fields.Selection(WIRE_SELECTION, string="Wire", required=True)
    l_qty = fields.Integer(string="LH Coils")
    r_qty = fields.Integer(string="RH Coils")
    length = fields.Float(string="Coil Length (in)", default=FULL_COIL, digits=(16, 2))

    @api.constrains("l_qty", "r_qty", "length")
    def _check_qty(self):
        for line in self:
            if line.l_qty < 0 or line.r_qty < 0:
                raise ValidationError(_("Coil counts cannot be negative."))
            if line.length <= 0:
                raise ValidationError(_("The coil length must be more than 0."))


class AaSpringBoxMove(models.TransientModel):
    _name = "aa.spring.box.move"
    _description = "Move Coils from a Box to the Floor"

    box_id = fields.Many2one("aa.spring.box", required=True, ondelete="cascade")
    line_ids = fields.One2many("aa.spring.box.move.line", "wizard_id", string="Coils")

    def _fill_lines(self, codes=None):
        """One line per coil product in the box; only `codes` (default_codes) when given."""
        self.ensure_one()
        counts = {}
        for quant in self.box_id._quants():
            if codes and quant.product_id.default_code not in codes:
                continue
            if quant.quantity - quant.reserved_quantity > 0.001:
                counts[quant.product_id] = counts.get(quant.product_id, 0) + 1
        self.line_ids = [(0, 0, {"product_id": product.id, "available": count, "qty": 0})
                         for product, count in sorted(counts.items(), key=lambda kv: kv[0].default_code)]

    def action_all(self):
        self.ensure_one()
        for line in self.line_ids:
            line.qty = line.available
        return self.action_confirm()

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.qty > 0)
        if not lines:
            raise UserError(_("Enter how many coils go to the floor."))
        floor = self.env["aa.spring.box"]._floor_location()
        Quant = self.env["stock.quant"].sudo()
        for line in lines:
            if line.qty > line.available:
                raise UserError(_("%(box)s only has %(n)s of %(coil)s.", box=self.box_id.name,
                                  n=line.available, coil=line.product_id.display_name))
            quants = Quant.search([
                ("location_id", "=", self.box_id.location_id.id),
                ("product_id", "=", line.product_id.id),
                ("quantity", ">", 0.001)], order="lot_id")
            quants = quants.filtered(lambda q: q.quantity - q.reserved_quantity > 0.001)[:line.qty]
            quants.move_quants(location_dest_id=floor,
                               message=_("%s to the floor", self.box_id.name))
        self.box_id._aa_close_if_empty()
        return {"type": "ir.actions.act_window_close"}


class AaSpringBoxMoveLine(models.TransientModel):
    _name = "aa.spring.box.move.line"
    _description = "Coils to Move to the Floor"

    wizard_id = fields.Many2one("aa.spring.box.move", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Coil", required=True, readonly=True)
    wire = fields.Char(compute="_compute_parts")
    inside_diameter = fields.Char(string="I.D.", compute="_compute_parts")
    hand = fields.Char(compute="_compute_parts")
    available = fields.Integer(string="In the Box", readonly=True)
    qty = fields.Integer(string="To the Floor")

    @api.depends("product_id")
    def _compute_parts(self):
        for line in self:
            parts = (line.product_id.default_code or "").split("-")
            if len(parts) == 4:
                line.wire = ".%s" % parts[1]
                line.inside_diameter = ID_LABELS.get(parts[2], parts[2])
                line.hand = "%sH" % parts[3]
            else:
                line.wire = line.inside_diameter = line.hand = False
