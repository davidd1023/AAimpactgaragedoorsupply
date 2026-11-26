import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from . import engine

DEPTHS = [("back", "Back"), ("front", "Front")]


def _order_number(ref):
    """'W/O 1051', '#1051' and '1051' are the same AA order."""
    ref = (ref or "").strip().lstrip("#").strip()
    return re.sub(r"(?i)^w\s*/?\s*o\s*#?\s*", "", ref).strip()


def _inches_label(inches):
    inches = round(inches or 0.0, 2)
    feet = int(inches // 12)
    rest = round(inches - feet * 12, 2)
    if not rest:
        return "%s'" % feet
    rest = ("%g" % rest)
    return "%s' %s\"" % (feet, rest)


class AaDoorBundle(models.Model):
    """What a forklift moves: one door or several, from one order or several,
    stacked with a board between doors. A bundle is what has a rack location."""
    _name = "aa.door.bundle"
    _description = "Door Bundle"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True)
    door_ids = fields.One2many("aa.door", "bundle_id", string="Doors")
    state = fields.Selection(
        [("draft", "Not Placed"), ("stored", "On Rack"), ("out", "Gone")],
        default="draft", tracking=True, required=True)
    side_id = fields.Many2one("aa.rack.side", string="Rack", tracking=True)
    level_id = fields.Many2one("aa.rack.level", string="Level", tracking=True)
    depth = fields.Selection(DEPTHS, tracking=True)
    arm_from = fields.Integer()
    arm_to = fields.Integer()
    pos_start = fields.Float(string="Left End (in)", help="Where the left end of the doors sits, from the first arm.")
    stack_seq = fields.Integer(string="Stack Position", default=1, help="1 is the bottom of the stack.")
    length = fields.Float(compute="_compute_size", store=True, string="Length (in)")
    height = fields.Float(compute="_compute_size", store=True, string="Stack Height (in)")
    location = fields.Char(compute="_compute_location", store=True)
    order_refs = fields.Char(compute="_compute_order_refs", store=True, string="Orders")
    received_on = fields.Datetime(default=fields.Datetime.now)
    move_ids = fields.One2many("aa.door.move", "bundle_id", string="History")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("aa.door.bundle") or _("New")
        return super().create(vals_list)

    @api.depends("door_ids.width", "door_ids.panels", "door_ids.state")
    def _compute_size(self):
        rules = self._rules()
        for bundle in self:
            doors = bundle.door_ids.filtered(lambda d: d.state == "stored")
            bundle.length = max(doors.mapped("width") or [0.0])
            bundle.height = engine.bundle_height(doors.mapped("panels"), rules)

    @api.depends("door_ids.order_ref", "door_ids.state")
    def _compute_order_refs(self):
        for bundle in self:
            refs = bundle.door_ids.filtered(lambda d: d.state == "stored").mapped("order_ref")
            bundle.order_refs = ", ".join(dict.fromkeys(r for r in refs if r))

    @api.depends("state", "level_id.code", "depth", "arm_from", "arm_to", "side_id.arm_positions", "stack_seq")
    def _compute_location(self):
        for bundle in self:
            if bundle.state != "stored" or not bundle.level_id:
                bundle.location = False
                continue
            bundle.location = " · ".join(filter(None, [
                bundle.level_id.code,
                bundle._arms_label(),
                dict(DEPTHS).get(bundle.depth),
                _("stack %s", bundle.stack_seq) if bundle.stack_seq > 1 else "",
            ]))

    def _arms_label(self):
        self.ensure_one()
        n = len(self.side_id._arms()) if self.side_id else 0
        a, b = self.arm_from, self.arm_to
        if n == 4:
            return {(0, 1): _("Left"), (2, 3): _("Right"), (1, 2): _("Middle"),
                    (0, 2): _("Full (arms 1-3)"), (1, 3): _("Full (arms 2-4)")}.get((a, b), "")
        if n == 3:
            return {(0, 1): _("Left"), (1, 2): _("Right"), (0, 2): _("Full")}.get((a, b), "")
        return _("Arms %(a)s-%(b)s", a=a + 1, b=b + 1)

    # ------------------------------------------------------------------
    # rules and the engine
    # ------------------------------------------------------------------
    @api.model
    def _rules(self):
        get = self.env["ir.config_parameter"].sudo().get_param

        def num(key, default):
            try:
                return float(get(key) or default)
            except (TypeError, ValueError):
                return default
        return engine.Rules(
            panel_thickness=num("aa_door_racks.panel_thickness", 3.25),
            spacer=num("aa_door_racks.spacer", 1.5),
            two_arm_max=num("aa_door_racks.two_arm_max", 120.0),
            fallback_max=num("aa_door_racks.fallback_max", 132.0),
            lift_room=num("aa_door_racks.lift_room", 5.0),
        )

    @api.model
    def _engine_state(self):
        sides = self.env["aa.rack.side"].search([])
        specs = [s._spec() for s in sides]
        placed = [engine.Placed(
            key=b.id, side=b.side_id.id, level=b.level_id.id, depth=b.depth,
            arm_from=b.arm_from, arm_to=b.arm_to, start=b.pos_start,
            length=b.length, height=b.height, seq=b.stack_seq)
            for b in self.search([("state", "=", "stored")])]
        placed += self.env["aa.rack.block"].search([])._placed()
        return specs, placed

    def _candidates(self, length=None, height=None):
        specs, placed = self._engine_state()
        return engine.candidates(
            specs, placed, length if length is not None else self.length,
            height if height is not None else self.height, self._rules(),
            exclude=self.id if self else None)

    def _place(self, cand, note=None):
        self.ensure_one()
        old = self.location
        self.write({
            "state": "stored", "side_id": cand.side, "level_id": cand.level,
            "depth": cand.depth, "arm_from": cand.arm_from, "arm_to": cand.arm_to,
            "pos_start": cand.start, "stack_seq": cand.seq,
        })
        self.env["aa.door.move"].create({
            "bundle_id": self.id, "from_location": old or False,
            "to_location": self.location, "note": note or False,
        })

    def action_find_spot(self):
        """Put the bundle where the engine says is best."""
        for bundle in self:
            if not bundle.door_ids:
                raise UserError(_("Add the doors in %s first.", bundle.name))
            cands = bundle._candidates()
            if not cands:
                raise UserError(_("There is no room on the racks for %s.", bundle.name))
            bundle._place(cands[0], note=_("Received"))
        return True

    def action_out(self):
        """Every door delivered: the bundle leaves its spot."""
        for bundle in self:
            bundle.door_ids.filtered(lambda d: d.state == "stored")._mark_delivered(_("Delivered by hand"))

    def _settle(self):
        """A bundle with no doors left on the rack frees its spot."""
        for bundle in self:
            if bundle.state == "stored" and not bundle.door_ids.filtered(lambda d: d.state == "stored"):
                old = bundle.location
                bundle.write({"state": "out"})
                self.env["aa.door.move"].create({
                    "bundle_id": bundle.id, "from_location": old, "to_location": False,
                    "note": _("All doors gone - spot freed"),
                })

    # ------------------------------------------------------------------
    # the rack board (client action)
    # ------------------------------------------------------------------
    @api.model
    def _is_admin(self):
        return self.env.user.has_group("stock.group_stock_manager")

    @api.model
    def board_data(self):
        sides = self.env["aa.rack.side"].search([])
        bundles = self.search([("state", "=", "stored")])
        out_sides = []
        for side in sides:
            arms = side._arms()
            levels = []
            for level in side.level_ids.filtered("active").sorted("number", reverse=True):
                levels.append({"id": level.id, "number": level.number, "code": level.code,
                               "clearance": level.clearance})
            out_sides.append({
                "id": side.id, "name": side.name, "arms": arms, "overhang": side.overhang,
                "min": arms[0] - side.overhang, "max": arms[-1] + side.overhang,
                "levels": levels,
            })
        free = self._free_summary(sides, bundles)
        return {
            "sides": out_sides,
            "bundles": [b._board_bundle() for b in bundles],
            "blocks": self._board_blocks(),
            "free": free,
            "admin": self._is_admin(),
            "rules": self._rules().__dict__,
        }

    @api.model
    def _board_blocks(self):
        out = []
        for block in self.env["aa.rack.block"].search([]):
            start, length = block._extent()
            out.append({"id": block.id, "side": block.side_id.id, "level": block.level_id.id,
                        "level_code": block.level_id.code, "depth": block.depth,
                        "arm_from": block.arm_from, "arm_to": block.arm_to,
                        "start": start, "length": length, "note": block.note or ""})
        return out

    @api.model
    def board_block(self, vals):
        """Close a spot (admin): level, depth (back/front/both), arms."""
        if not self._is_admin():
            raise AccessError(_("Only an Inventory administrator can close a spot."))
        level = self.env["aa.rack.level"].browse(int(vals["level"]))
        a, b = int(vals["arm_from"]), int(vals["arm_to"])
        n = len(level.side_id._arms())
        if not (0 <= a < b < n):
            raise UserError(_("Pick which part of the level to close."))
        depths = ("back", "front") if vals.get("depth") == "both" else (vals.get("depth"),)
        busy = self.search([("state", "=", "stored"), ("level_id", "=", level.id),
                            ("depth", "in", depths), ("arm_from", "<=", b), ("arm_to", ">=", a)])
        if busy:
            raise UserError(_("%(spot)s holds %(bundles)s - move them first.",
                              spot=level.code, bundles=", ".join(busy.mapped("name"))))
        self.env["aa.rack.block"].create({
            "level_id": level.id, "depth": vals.get("depth") or "both",
            "arm_from": a, "arm_to": b, "note": (vals.get("note") or "").strip() or False})
        return True

    @api.model
    def board_block_many(self, spots, note=False):
        """Close several spots at once, picked by clicking on the map.

        `spots` is a list of {level, depth, arm_from, arm_to}, one per clicked
        half of a row. Halves next to each other on the same row become one
        closed spot, and a back and front closed the same way become one
        "Back and Front" spot, so closing all of rack B leaves 5 records, not 20.
        One transaction: a spot holding a bundle refuses the whole lot."""
        if not self._is_admin():
            raise AccessError(_("Only an Inventory administrator can close a spot."))
        rows = {}
        for s in spots or []:
            key = (int(s["level"]), s["depth"])
            rows.setdefault(key, []).append((int(s["arm_from"]), int(s["arm_to"])))
        if not rows:
            raise UserError(_("Click the spots to close first."))
        merged = {}
        for key, parts in rows.items():
            parts.sort()
            out = [list(parts[0])]
            for a, b in parts[1:]:
                if a <= out[-1][1] + 1:
                    out[-1][1] = max(out[-1][1], b)
                else:
                    out.append([a, b])
            merged[key] = [tuple(p) for p in out]
        made = 0
        for (level, depth), parts in sorted(merged.items()):
            if depth == "front" and merged.get((level, "back")) == parts:
                continue                              # done with the back, as "both"
            if depth == "back" and merged.get((level, "front")) == parts:
                depth = "both"
            for a, b in parts:
                self.board_block({"level": level, "depth": depth, "arm_from": a,
                                  "arm_to": b, "note": note})
                made += 1
        return made

    @api.model
    def board_unblock(self, block_id):
        if not self._is_admin():
            raise AccessError(_("Only an Inventory administrator can open a spot."))
        self.env["aa.rack.block"].browse(block_id).unlink()
        return True

    @api.model
    def board_lookup(self, ref):
        """The doors of an AA Impact order, read off the Supply order whose
        PO Number carries that W/O number ("W/O 1051 - customer"). None found
        means it is not an AA order and the sizes must be typed."""
        ref = (ref or "").strip().lstrip("#").strip()
        if not ref:
            return {"found": False}
        num = _order_number(ref)
        order = self._aa_find_order(num)
        if not order:
            return {"found": False, "ref": num}
        customer = re.sub(r"(?i)^\s*(?:w\s*/?\s*o\s*#?\s*)?%s\s*[-:]*\s*" % re.escape(num), "",
                          order.client_order_ref or "").strip()
        doors = []
        rows = order._aa_door_rows() if hasattr(order, "_aa_door_rows") else []
        kits = order._aa_kit_lines() if hasattr(order, "_aa_kit_lines") else order.order_line.filtered(
            lambda l: "Hardware Kit" in (l.product_id.display_name or "") and l.product_uom_qty > 0)
        for idx, row in enumerate(rows):
            kit = kits[idx] if idx < len(kits) else False
            m = re.search(r"(\d+)\s*Panels?", kit.product_id.display_name if kit else "")
            for _i in range(max(1, int(row.get("qty") or 1))):
                doors.append({"width": row.get("width_in") or 0, "height": row.get("height_in") or 0,
                              "panels": int(m.group(1)) if m else 0})
        stored = self.env["aa.door"].search_count([("state", "=", "stored"), ("order_ref", "=", num)])
        return {"found": True, "ref": num, "order": order.name, "customer": customer,
                "doors": doors, "on_rack": stored}

    @api.model
    def _aa_find_order(self, num):
        if not num:
            return self.env["sale.order"]
        orders = self.env["sale.order"].sudo().search(
            [("client_order_ref", "ilike", num), ("state", "!=", "cancel")], order="id desc", limit=40)
        rx = re.compile(r"(?i)^\s*(?:w\s*/?\s*o\s*#?\s*)?%s(?:\b|$)" % re.escape(num))
        return next((o for o in orders if rx.search(o.client_order_ref or "")), self.env["sale.order"])

    def _board_bundle(self):
        self.ensure_one()
        doors = self.door_ids.filtered(lambda d: d.state == "stored")
        return {
            "id": self.id, "name": self.name, "side": self.side_id.id, "level": self.level_id.id,
            "depth": self.depth, "arm_from": self.arm_from, "arm_to": self.arm_to,
            "start": self.pos_start, "length": self.length, "height": self.height,
            "seq": self.stack_seq, "location": self.location, "orders": self.order_refs or "",
            "doors": [d._board_door() for d in doors],
        }

    @api.model
    def _free_summary(self, sides, bundles):
        """How many more doors fit right now, counted for a typical small
        (9', 4 panels) and a typical big (16', 4 panels) door."""
        rules = self._rules()
        small_h = engine.bundle_height([4], rules)
        specs, placed = self._engine_state()
        result = {}
        for label, length in (("small", 108.0), ("big", 192.0)):
            # place copies one after another until nothing fits
            sim = list(placed)
            count = 0
            while count < 200:
                cands = engine.candidates(specs, sim, length, small_h, rules)
                cands = [c for c in cands if not c.stacked]
                if not cands:
                    break
                c = cands[0]
                sim.append(engine.Placed(key=-1 - count, side=c.side, level=c.level, depth=c.depth,
                                         arm_from=c.arm_from, arm_to=c.arm_to, start=c.start,
                                         length=length, height=small_h, seq=1))
                count += 1
            result[label] = count
        total_rows = sum(len(s.level_ids.filtered("active")) * 2 for s in sides)
        used_rows = len({(b.level_id.id, b.depth) for b in bundles})
        result["rows_total"] = total_rows
        result["rows_empty"] = total_rows - used_rows
        return result

    @api.model
    def board_search(self, term):
        term = (term or "").strip()
        if not term:
            return []
        doors = self.env["aa.door"].search([
            ("state", "=", "stored"),
            "|", "|", ("order_ref", "ilike", term), ("customer", "ilike", term),
            ("bundle_id.name", "ilike", term)], limit=50)
        return [d._board_door() for d in doors]

    @api.model
    def board_suggest(self, doors, bundle_id=False):
        """Where a new bundle of these doors (or an existing bundle, moved)
        can go. doors: [{"width": in, "panels": n}]"""
        rules = self._rules()
        if bundle_id:
            bundle = self.browse(bundle_id)
            length, height = bundle.length, bundle.height
            exclude = bundle.id
        else:
            widths = [float(d.get("width") or 0) for d in doors]
            if not widths or min(widths) <= 0:
                raise UserError(_("Every door needs its width."))
            length = max(widths)
            height = engine.bundle_height([int(d.get("panels") or 0) for d in doors], rules)
            exclude = None
        specs, placed = self._engine_state()
        cands = engine.candidates(specs, placed, length, height, rules, exclude=exclude)
        levels = {lv.id: lv for lv in self.env["aa.rack.level"].browse({c.level for c in cands})}
        return {
            "length": length, "height": height,
            "spots": [{
                "side": c.side, "level": c.level, "level_code": levels[c.level].code,
                "depth": c.depth, "arm_from": c.arm_from, "arm_to": c.arm_to,
                "start": c.start, "stacked": c.stacked, "seq": c.seq,
                "stack_height": c.stack_height, "score": c.score, "best": idx == 0,
                "why": self._spot_reasons(c, rules),
            } for idx, c in enumerate(cands[:12])],
        }

    @api.model
    def _spot_reasons(self, cand, rules):
        out = []
        for r in cand.reasons:
            if r == "stack":
                out.append(_("On top of a bundle already there - uses no new arms"))
            elif r == "beside":
                out.append(_("Beside bundles already in this row"))
            elif r == "new_row":
                out.append(_("Starts an empty row"))
            elif r == "back":
                out.append(_("Back row - the front stays open"))
            elif isinstance(r, (list, tuple)) and r[0] == "room":
                out.append(_('%s" left above (%s" kept for the forklift)', r[1], rules.lift_room))
        return out

    # ---------- scanning the AA Impact door sticker ----------
    # The sticker's QR / barcode reads   AAD|<W/O>|<door #>|<width in>|<height in>|<panels>
    # e.g. AAD|1051|1|107|87.5|4  - one scan = one whole door. A code that is
    # only the W/O number works too: the sizes come from the Supply order.
    SCAN_RX = re.compile(r"^\s*AAD[|;,]([^|;,]+)[|;,](\d*)[|;,]([\d.]*)[|;,]([\d.]*)[|;,](\d*)", re.I)

    @api.model
    def board_scan(self, code, taken=None):
        """One sticker scanned. taken: [{order_ref, door_no}] already in this bundle.
        Returns {ok, door, msg, level} - level is info / warning / danger."""
        code = (code or "").strip()
        if not code:
            return {"ok": False, "msg": _("Nothing was scanned."), "level": "warning"}
        taken = taken or []
        m = self.SCAN_RX.match(code)
        if m:
            num = _order_number(m.group(1))
            door_no = int(m.group(2) or 0)
            width, height = float(m.group(3) or 0), float(m.group(4) or 0)
            panels = int(m.group(5) or 0)
        else:
            num, door_no, width, height, panels = _order_number(code), 0, 0.0, 0.0, 0
        info = self.board_lookup(num)
        if not door_no:
            door_no = 1 + sum(1 for t in taken if _order_number(t.get("order_ref")) == num)
        if any(_order_number(t.get("order_ref")) == num and int(t.get("door_no") or 0) == door_no for t in taken):
            return {"ok": False, "level": "warning",
                    "msg": _("Door %(n)s of order %(o)s is already scanned - one sticker per door.", n=door_no, o=num)}
        doors = info.get("doors") or []
        if not (width and panels) and doors:
            if door_no > len(doors):
                return {"ok": False, "level": "danger",
                        "msg": _("Order %(o)s has %(c)s door(s) and they are all scanned.", o=num, c=len(doors))}
            d = doors[door_no - 1]
            width, height, panels = width or d["width"], height or d["height"], panels or d["panels"]
        door = {"order_ref": num, "door_no": door_no, "customer": info.get("customer") or "",
                "order": info.get("order") or "", "width": width, "height": height, "panels": panels}
        msgs, level = [], "info"
        stored = self.env["aa.door"].search([("state", "=", "stored"), ("order_ref", "=", num)])
        same = stored.filtered(lambda d: d.door_no == door_no)
        if not same and stored and not stored.filtered("door_no") and len(stored) >= max(len(doors), 1):
            same = stored[:1]
        if same:
            msgs.append(_("Careful: door %(n)s of order %(o)s is already on the racks at %(l)s.",
                          n=door_no, o=num, l=same[:1].bundle_id.location))
            level = "warning"
        if not (width and panels):
            msgs.append(_("Not an AA Impact order - type the door size.") if not info.get("found")
                        else _("%s has no door sizes - type them.", info.get("order")))
            level = "warning"
        return {"ok": True, "door": door, "msg": " ".join(msgs), "level": level}

    @api.model
    def board_receive(self, doors, spot):
        """Create the bundle and put it on the chosen spot."""
        if not doors:
            raise UserError(_("Add at least one door."))
        bundle = self.create({"door_ids": [(0, 0, {
            "order_ref": _order_number(d.get("order_ref")),
            "door_no": int(d.get("door_no") or 0),
            "customer": (d.get("customer") or "").strip() or False,
            "width": float(d.get("width") or 0),
            "panels": int(d.get("panels") or 0),
        }) for d in doors]})
        bundle._place_at(spot, note=_("Received"))
        return bundle._board_bundle()

    def _place_at(self, spot, note=None, force=False):
        self.ensure_one()
        specs, placed = self._engine_state()
        cand = engine.fits(specs, placed, self.length, self.height, self._rules(),
                           spot["side"], spot["level"], spot["depth"],
                           spot["arm_from"], spot["arm_to"], exclude=self.id)
        if not cand:
            if not force:
                raise UserError(_("%s does not fit there any more - pick another spot.", self.name))
            cand = engine.Candidate(spot["side"], spot["level"], spot["depth"], spot["arm_from"],
                                    spot["arm_to"], spot.get("start", 0.0), False, self.height, 0, 1)
        self._place(cand, note=note)

    @api.model
    def board_move(self, bundle_id, spot, force=False):
        if not self._is_admin():
            raise AccessError(_("Only an Inventory administrator can move bundles."))
        bundle = self.browse(bundle_id)
        if force and not spot.get("start"):
            spot = dict(spot, start=0.0)
        bundle._place_at(spot, note=_("Moved by %s", self.env.user.name), force=force)
        return True

    @api.model
    def board_deliver(self, door_ids):
        doors = self.env["aa.door"].browse(door_ids).filtered(lambda d: d.state == "stored")
        doors._mark_delivered(_("Delivered by %s", self.env.user.name))
        return True

    @api.model
    def board_remove(self, bundle_id=False, door_ids=None, mode="delivered"):
        """Take doors (or a whole bundle) off the rack.
        delivered - they left with the customer: kept in the history.
        mistake   - they were entered wrongly: deleted (admin only)."""
        if bundle_id:
            bundle = self.browse(bundle_id)
            doors = bundle.door_ids.filtered(lambda d: d.state == "stored")
        else:
            doors = self.env["aa.door"].browse(door_ids or []).filtered(lambda d: d.state == "stored")
            bundle = doors.mapped("bundle_id")
        if mode == "mistake":
            if not self._is_admin():
                raise AccessError(_("Only an Inventory administrator can delete doors entered by mistake."))
            for b in bundle.sudo():
                left = b.door_ids.filtered(lambda d: d.state == "stored") - doors.sudo()
                b.message_post(body=_("Deleted as entered by mistake: %s", ", ".join(doors.filtered(
                    lambda d: d.bundle_id == b).mapped("order_ref"))))
                if not left and not b.door_ids.filtered(lambda d: d.state == "delivered"):
                    b.unlink()
                    continue
                doors.sudo().filtered(lambda d: d.bundle_id == b).unlink()
                b._settle()
            return True
        doors._mark_delivered(_("Taken off the rack by %s", self.env.user.name))
        return True

    @api.model
    def board_split(self, door_id):
        """Take one door out of its bundle into a bundle of its own (admin),
        and return the new bundle so the board can place it."""
        if not self._is_admin():
            raise AccessError(_("Only an Inventory administrator can split a bundle."))
        door = self.env["aa.door"].browse(door_id)
        old = door.bundle_id
        new = self.create({})
        door.bundle_id = new
        old.invalidate_recordset(["length", "height"])
        old._settle()
        return new._board_bundle()


class AaDoor(models.Model):
    """One door of an AA Impact order, sitting in a bundle."""
    _name = "aa.door"
    _description = "Door on Rack"
    _order = "id desc"
    _rec_name = "order_ref"

    bundle_id = fields.Many2one("aa.door.bundle", required=True, ondelete="cascade", index=True)
    order_ref = fields.Char(string="AA Order #", required=True, index=True)
    door_no = fields.Integer(string="Door #", help="Which door of the order (1, 2...) - from the sticker scan")
    customer = fields.Char()
    width = fields.Float(string="Width (in)", required=True)
    panels = fields.Integer(required=True, default=4)
    state = fields.Selection([("stored", "On Rack"), ("delivered", "Delivered")],
                             default="stored", required=True)
    delivered_on = fields.Datetime()
    sale_order_id = fields.Many2one("sale.order", string="Supply Order",
                                    compute="_compute_sale_order", store=True, readonly=False)
    location = fields.Char(related="bundle_id.location")
    width_label = fields.Char(compute="_compute_width_label")

    @api.depends("width")
    def _compute_width_label(self):
        for door in self:
            door.width_label = _inches_label(door.width)

    @api.depends("order_ref")
    def _compute_sale_order(self):
        """The Supply order whose PO Number is this AA Impact order number."""
        for door in self:
            door.sale_order_id = self.env["aa.door.bundle"]._aa_find_order(
                _order_number(door.order_ref))

    def _board_door(self):
        self.ensure_one()
        return {"id": self.id, "order_ref": self.order_ref, "door_no": self.door_no or 0,
                "customer": self.customer or "",
                "width": self.width, "width_label": self.width_label, "panels": self.panels,
                "bundle": self.bundle_id.id, "bundle_name": self.bundle_id.name,
                "location": self.location or "", "sale_order": self.sale_order_id.display_name or ""}

    def _mark_delivered(self, note):
        if not self:
            return
        self.write({"state": "delivered", "delivered_on": fields.Datetime.now()})
        for door in self:
            self.env["aa.door.move"].create({
                "bundle_id": door.bundle_id.id, "door_id": door.id,
                "from_location": door.bundle_id.location, "to_location": False,
                "note": note,
            })
        bundles = self.mapped("bundle_id")
        bundles.invalidate_recordset(["length", "height", "order_refs"])
        bundles._settle()


class AaDoorMove(models.Model):
    _name = "aa.door.move"
    _description = "Door Rack History"
    _order = "id desc"

    bundle_id = fields.Many2one("aa.door.bundle", ondelete="cascade", index=True)
    door_id = fields.Many2one("aa.door", ondelete="set null")
    from_location = fields.Char()
    to_location = fields.Char()
    note = fields.Char()
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now)
