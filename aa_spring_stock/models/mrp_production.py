import json
import logging

from odoo import _, api, fields, models

from odoo.addons.aa_shop_floor.models.mrp_production import inches_label

from .coil import ID_LABELS, SOURCES, pick_piece, place_of, spring_cuts, wire_code, id_code

_logger = logging.getLogger(__name__)

HAND_LABELS = {"L": "LH", "R": "RH"}
# A piece left shorter than this after a cut is scrapped (owner, 2026-10-19).
MIN_LEFTOVER = 16.0


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_spring_cut_ids = fields.One2many("aa.spring.cut", "production_id", string="Spring Cuts")

    # --- planning: which piece each spring is cut from ---------------------------

    def _aa_spring_spec(self):
        self.ensure_one()
        if self.aa_station_kind != "spring" or not self.aa_spring_spec_json:
            return None
        try:
            spec = json.loads(self.aa_spring_spec_json)
        except ValueError:
            return None
        return spec if isinstance(spec, dict) and spec.get("items") else None

    def _aa_coil_pieces(self, product):
        """[(source, available inches, lot name, quant)] for one coil product."""
        self.ensure_one()
        quants = self.env["stock.quant"].sudo().search([
            ("product_id", "=", product.id),
            ("location_id", "child_of", self.location_src_id.id),
            ("location_id.usage", "=", "internal"),
            ("quantity", ">", 0),
        ])
        pieces = []
        for quant in quants:
            source = place_of(quant.location_id)
            available = quant.quantity - quant.reserved_quantity
            if source in SOURCES and available > 1e-6:
                pieces.append((source, available, quant.lot_id.name or "", quant))
        return pieces

    def _aa_coil_move(self, product):
        """The raw move that consumes this coil, created on first use."""
        self.ensure_one()
        move = self.move_raw_ids.filtered(
            lambda m: m.product_id == product and m.state not in ("done", "cancel"))[:1]
        if not move:
            values = self._get_move_raw_values(product, 0.0, product.uom_id)
            move = self.env["stock.move"].sudo().create(values)
            move._action_confirm()
        return move

    def _aa_plan_coil_cuts(self):
        """Give every spring of the order the piece it is cut from, and reserve it.

        Never raises: a spring that cannot be matched to a coil is recorded as
        such and the office sees it on the order and in the cut history.
        """
        Cut = self.env["aa.spring.cut"].sudo()
        Product = self.env["product.product"].sudo()
        for production in self:
            if production.state in ("done", "cancel") or production.aa_spring_cut_ids:
                continue
            spec = production._aa_spring_spec()
            if not spec:
                continue
            problems = []
            for cut in spring_cuts(spec, production.product_qty):
                values = {
                    "production_id": production.id,
                    "role": cut["role"],
                    "hand": cut["hand"],
                    "wire": wire_code(cut["wire"]) or ("%.4f" % float(cut["wire"] or 0)).lstrip("0"),
                    "inside_diameter": ID_LABELS.get(id_code(cut["id"]) or "", "%g\"" % float(cut["id"] or 0)),
                    "length": cut["length"],
                }
                product = cut["code"] and Product.search([("default_code", "=", cut["code"])], limit=1)
                if not product:
                    values.update(state="untracked", note=_("No coil product %s", cut["code"] or "for this wire / I.D."))
                    problems.append(values)
                    Cut.create(values)
                    continue
                values["product_id"] = product.id
                piece = pick_piece(production._aa_coil_pieces(product), cut["length"])
                if not piece:
                    values.update(state="short", note=_("No piece of %s is long enough", product.default_code))
                    problems.append(values)
                    Cut.create(values)
                    continue
                source, available, _lot, quant = piece
                move = production._aa_coil_move(product)
                move.product_uom_qty += cut["length"]
                self.env["stock.move.line"].sudo().create({
                    "move_id": move.id,
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "lot_id": quant.lot_id.id,
                    "location_id": quant.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "quantity": cut["length"],
                })
                values.update(lot_id=quant.lot_id.id, source=source,
                              remaining=round(available - cut["length"], 2))
                Cut.create(values)
            if problems:
                production.message_post(body=_(
                    "Spring coil not taken from inventory for: %s. Check the coil stock "
                    "(Inventory > Springs) before cutting.",
                    ", ".join("%s %s .%s %s" % (HAND_LABELS[p["hand"]], p["role"], p["wire"],
                                                 p["inside_diameter"]) for p in problems)))
            if "aa_shop_spec" in production._fields:
                production._compute_aa_shop_spec()

    def _aa_safe_plan_coil_cuts(self):
        for production in self:
            try:
                with self.env.cr.savepoint():
                    production._aa_plan_coil_cuts()
            except Exception as error:  # never block an order over the coil plan
                _logger.exception("aa_spring_stock: coil plan for %s failed", production.name)
                production.message_post(body=_("The spring coil could not be reserved: %s", error))

    def _aa_coil_plan_intact(self):
        """True when every planned cut still has its reserved piece."""
        self.ensure_one()
        planned = self.aa_spring_cut_ids.filtered(lambda c: c.state == "planned")
        for product in planned.product_id:
            need = sum(planned.filtered(lambda c: c.product_id == product).mapped("length"))
            moves = self.move_raw_ids.filtered(lambda m: m.product_id == product and m.state != "cancel")
            have = sum(moves.move_line_ids.filtered("lot_id").mapped("quantity"))
            if have + 1e-6 < need:
                return False
        return True

    def _aa_replan_coil_cuts(self):
        """Start the plan again (a reservation was undone by hand)."""
        self.ensure_one()
        coil_moves = self.move_raw_ids.filtered(
            lambda m: (m.product_id.default_code or "").startswith("COIL-") and m.state not in ("done", "cancel"))
        coil_moves.move_line_ids.unlink()
        coil_moves.write({"product_uom_qty": 0.0})
        self.aa_spring_cut_ids.filtered(lambda c: c.state != "done").unlink()
        self._aa_plan_coil_cuts()

    # --- hooks ---------------------------------------------------------------------

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered(lambda p: p.aa_station_kind == "spring")._aa_safe_plan_coil_cuts()
        return result

    def button_mark_done(self):
        springs = self.filtered(lambda p: p.aa_station_kind == "spring" and p.state not in ("done", "cancel"))
        for production in springs:
            if not production.aa_spring_cut_ids:
                production._aa_safe_plan_coil_cuts()
            elif not production._aa_coil_plan_intact():
                production._aa_replan_coil_cuts()
            coil_moves = production.move_raw_ids.filtered(
                lambda m: (m.product_id.default_code or "").startswith("COIL-")
                and m.state not in ("done", "cancel"))
            coil_moves.filtered(lambda m: not m.product_uom_qty).write({"state": "cancel"})
            coil_moves = coil_moves.filtered(lambda m: m.product_uom_qty)
            coil_moves.move_line_ids.write({"picked": True})
            coil_moves.write({"picked": True})
        result = super().button_mark_done()
        springs.filtered(lambda p: p.state == "done")._aa_after_cut()
        return result

    def _aa_after_cut(self):
        """Book the cuts, and move an opened box coil to the floor."""
        Quant = self.env["stock.quant"].sudo()
        for production in self:
            cuts = production.aa_spring_cut_ids.filtered(lambda c: c.state == "planned")
            boxed = set()
            scrapped = set()
            for cut in cuts.sorted("id"):
                quant = Quant.search([
                    ("product_id", "=", cut.product_id.id), ("lot_id", "=", cut.lot_id.id),
                    ("location_id.usage", "=", "internal"), ("quantity", ">", 0)],
                    order="quantity desc", limit=1)
                left = round(quant.quantity, 2) if quant else 0.0
                values = {"state": "done", "date": fields.Datetime.now(), "remaining": left}
                # Under 16" a piece is thrown away (owner, 2026-10-19). Only once
                # nothing else of this order still counts on the same piece.
                if quant and left < MIN_LEFTOVER and not quant.reserved_quantity \
                        and (cut.product_id.id, cut.lot_id.id) not in scrapped:
                    production._aa_scrap_leftover(quant)
                    scrapped.add((cut.product_id.id, cut.lot_id.id))
                    values.update(remaining=0.0, note=_('%s" left over, scrapped', "%g" % left))
                cut.write(values)
                if cut.source == "Boxes" and (cut.product_id.id, cut.lot_id.id) not in scrapped:
                    boxed.add((cut.product_id.id, cut.lot_id.id))
            if not boxed:
                continue
            floor = self.env["stock.location"].sudo().search([
                ("name", "=", "Floor"), ("usage", "=", "internal"),
                ("id", "child_of", production.location_src_id.id)], limit=1)
            if not floor:
                continue
            for product_id, lot_id in boxed:
                quants = Quant.search([
                    ("product_id", "=", product_id), ("lot_id", "=", lot_id),
                    ("location_id.usage", "=", "internal"), ("quantity", ">", 0)])
                quants = quants.filtered(
                    lambda q: not q.reserved_quantity and place_of(q.location_id) == "Boxes")
                if quants:
                    try:
                        with self.env.cr.savepoint():
                            quants.move_quants(location_dest_id=floor,
                                               message=_("Opened for %s", production.aa_wo_number or production.name))
                    except Exception:
                        _logger.exception("aa_spring_stock: could not move %s to the floor", quants.lot_id.name)

    def _aa_scrap_leftover(self, quant):
        """Throw away a leftover too short to make a spring from."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                scrap = self.env["stock.scrap"].sudo().create({
                    "product_id": quant.product_id.id,
                    "product_uom_id": quant.product_id.uom_id.id,
                    "lot_id": quant.lot_id.id,
                    "scrap_qty": quant.quantity,
                    "location_id": quant.location_id.id,
                    "origin": self.aa_wo_number or self.name,
                    "company_id": self.company_id.id,
                })
                scrap.do_scrap()
        except Exception:
            _logger.exception("aa_spring_stock: could not scrap %s", quant.lot_id.name)

    def action_cancel(self):
        result = super().action_cancel()
        self.aa_spring_cut_ids.filtered(lambda c: c.state != "done").unlink()
        return result

    # --- the Springs card --------------------------------------------------------------

    @api.depends("aa_spring_cut_ids.state", "aa_spring_cut_ids.lot_id")
    def _compute_aa_shop_spec(self):
        return super()._compute_aa_shop_spec()

    def _aa_custom_spring_rows(self, spec):
        rows = super()._aa_custom_spring_rows(spec)
        for cut in self.aa_spring_cut_ids.sorted(lambda c: (c.hand, c.role != "Outer", c.id)):
            what = "%s %s" % (HAND_LABELS.get(cut.hand, ""), cut.role or "Spring")
            if cut.state in ("planned", "done"):
                where = {"Rack": "Rack piece", "Floor": "Floor coil", "Boxes": "Box coil (open it)"}
                rows.append(("Cut from", '%s %s: %s · %s' % (
                    what, inches_label(cut.length), cut.lot_id.name, where.get(cut.source, cut.source or ""))))
            else:
                rows.append(("Cut from", "%s %s: NO COIL IN INVENTORY - tell the office" % (
                    what, inches_label(cut.length))))
        return rows
