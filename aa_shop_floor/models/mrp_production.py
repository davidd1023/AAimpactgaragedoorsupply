import json
import math
import re

from odoo import api, fields, models

# How the shop writes the three single I.D.s and the duplex outer.
ID_LABELS = {2.625: '2 5/8"', 3.75: '3 3/4"', 5.25: '5 1/4"', 6.0: '6"'}
FILLER_ID = 5.25

# Finished stock springs: SPR-262-2.625-R
# Prepared track products, as named in the catalogue:
#   3" Horizontal Track - 108" White
#   3" Vertical Track 88" - 8' Door Height White
HORIZONTAL_TRACK = re.compile(r'^(\d)" Horizontal Track -\s+(\d+)" (White|Black)$')
VERTICAL_TRACK = re.compile(r'^(\d)" Vertical Track (\d+)" - (\d+)\' Door Height (White|Black)$')
# The raw stock they are cut from: 3" Horizontal Track RAW - 9'6" White
RAW_LENGTH = re.compile(r"RAW\s*-\s*(\d+)'\s*(?:(\d+)\")?")

STOCK_SPRING_CODE = re.compile(r"^SPR-(\d{3,4})-(\d+(?:\.\d+)?)-([LR])$")


def wire_label(wire):
    """0.2625 -> '.2625', 0.25 -> '.250', the way the shop writes wire."""
    text = "%.4f" % float(wire)
    if text.endswith("0"):
        text = text[:-1]
    return text.lstrip("0")


def inches_label(value):
    """32.25 -> '32 1/4"' (nearest eighth)."""
    value = float(value)
    whole = int(math.floor(value))
    eighths = int(round((value - whole) * 8))
    if eighths == 8:
        whole, eighths = whole + 1, 0
    if not eighths:
        return '%d"' % whole
    num, den = eighths, 8
    while num % 2 == 0:
        num, den = num // 2, den // 2
    return '%d %d/%d"' % (whole, num, den)


def id_label(diameter):
    diameter = round(float(diameter), 4)
    return ID_LABELS.get(diameter) or inches_label(diameter)


def qty_label(value):
    return "%g" % value


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_sale_line_id = fields.Many2one(
        "sale.order.line", string="Sale Order Line", copy=False, index=True, readonly=True)
    aa_spring_spec_json = fields.Text(string="Spring Spec (data)", copy=False, readonly=True)
    aa_station_kind = fields.Selection(
        [("spring", "Spring"), ("kit", "Hardware Kit"), ("cable", "Lift Cables")],
        string="Station Job", copy=False, readonly=True)
    # Lift cable lines packed in this kit's box (shown on the kit card instead of
    # a card of their own).
    aa_cable_line_ids = fields.Many2many(
        "sale.order.line", "aa_mrp_production_cable_line_rel", "production_id", "line_id",
        string="Lift Cables in the Box", copy=False, readonly=True)
    # Which checkable rows of the card the worker has ticked (JSON list of row
    # numbers). "Put it in the box, tick it" (owner, 2026-10-14).
    aa_packed = fields.Text(string="Packed Rows", copy=False)
    # "Label|Value" rows, one per line. Read by the Shop Floor card.
    aa_shop_spec = fields.Text(
        string="Shop Floor Instructions", compute="_compute_aa_shop_spec", store=True)

    @api.depends("aa_spring_spec_json", "aa_station_kind", "aa_sale_line_id", "aa_cable_line_ids",
                 "product_id", "product_qty", "move_raw_ids.product_id", "move_raw_ids.product_uom_qty")
    def _compute_aa_shop_spec(self):
        for production in self:
            if production.aa_station_kind == "kit":
                rows = production._aa_kit_rows()
            elif production.aa_station_kind == "cable":
                rows = production._aa_cable_rows()
            else:
                rows = production._aa_track_rows() or production._aa_spring_rows()
            production.aa_shop_spec = "\n".join("|".join(str(x) for x in row) for row in rows) or False

    def aa_toggle_packed(self, key):
        """Tick / untick one row of the Shop Floor card. Returns the ticked rows."""
        self.ensure_one()
        try:
            keys = set(json.loads(self.aa_packed or "[]"))
        except ValueError:
            keys = set()
        keys ^= {str(key)}
        self.aa_packed = json.dumps(sorted(keys, key=lambda k: int(k) if k.isdigit() else 0))
        return sorted(keys)

    # --- springs ----------------------------------------------------------------

    def _aa_spring_rows(self):
        self.ensure_one()
        if self.aa_spring_spec_json:
            try:
                spec = json.loads(self.aa_spring_spec_json)
            except ValueError:
                spec = None
            if isinstance(spec, dict) and spec.get("items"):
                return self._aa_custom_spring_rows(spec)
        return self._aa_stock_spring_rows()

    def _aa_custom_spring_rows(self, spec):
        """A spring from Spring Engineering. LH/RH in the spec are per order line
        unit, so they are multiplied by the MO quantity."""
        qty = self.product_qty or 1.0
        items = spec["items"]
        assembly = spec.get("assembly") or "Single"
        lh = (spec.get("lh") or 0) * qty
        rh = (spec.get("rh") or 0) * qty
        rows = []

        if len(items) > 1:
            rows.append(("Assembly", "%s (%s)" % (
                assembly, " inside ".join(id_label(i["id"]) for i in reversed(items)))))
            for item in items:
                rows.append((item.get("role") or "Spring", '%s wire · %s I.D. · %s long' % (
                    wire_label(item["wire"]), id_label(item["id"]), inches_label(item["length"]))))
        else:
            item = items[0]
            rows.append(("Assembly", assembly))
            rows.append(("Wire", wire_label(item["wire"])))
            rows.append(("I.D.", id_label(item["id"])))
            rows.append(("Length", inches_label(item["length"])))

        rows.append(("LH", qty_label(lh)))
        rows.append(("RH", qty_label(rh)))
        if len(items) > 1:
            rows.append(("Note", "Each LH / RH is a full set (outer + inner), both the same hand"))

        filler = [i for i in items if round(float(i["id"]), 4) == FILLER_ID]
        if filler:
            rows.append(("Filler", "Plastic filler in each 5 1/4\" spring, cut to %s" % (
                inches_label(filler[0]["length"]))))

        door = spec.get("door") or {}
        if door.get("weight"):
            rows.append(("Door", "%s lb · %s · %s cycles" % (
                door["weight"], door.get("height") or "", "{:,}".format(int(door.get("cycles") or 0)))))
        return rows

    def _aa_stock_spring_rows(self):
        """A finished stock spring, read from its code SPR-<wire>-<ID>-<L/R>."""
        hit = STOCK_SPRING_CODE.match(self.product_id.default_code or "")
        if not hit:
            return []
        wire, diameter, hand = hit.groups()
        qty = qty_label(self.product_qty or 1.0)
        return [
            ("Wire", "." + wire),
            ("I.D.", id_label(diameter)),
            ("LH", qty if hand == "L" else "0"),
            ("RH", qty if hand == "R" else "0"),
        ]

    # --- track prep ---------------------------------------------------------------
    # Prepared tracks come from Odoo's own Manufacture route with the owner's
    # BoMs (RAW track x2, and for verticals the flag angles, jamb brackets and
    # lag screws). Each MO unit is one LH + RH pair.

    def _aa_track_rows(self):
        name = (self.product_id.with_context(display_default_code=False).display_name or "").strip()
        horizontal = HORIZONTAL_TRACK.match(name)
        vertical = VERTICAL_TRACK.match(name)
        if not (horizontal or vertical):
            return []
        pairs = self.product_qty or 1.0
        if horizontal:
            size, length, colour = horizontal.groups()
            rows = [("Track", '%s" Horizontal · %s' % (size, colour))]
        else:
            size, length, door, colour = vertical.groups()
            rows = [("Track", '%s" Vertical · %s' % (size, colour)), ("Door height", "%s'" % door)]
        length = float(length)

        raw = self.move_raw_ids.filtered(lambda m: "RAW" in (m.product_id.name or ""))[:1]
        hit = raw and RAW_LENGTH.search(raw.product_id.name or "")
        raw_inches = (int(hit.group(1)) * 12 + int(hit.group(2) or 0)) if hit else 0
        if not raw_inches or raw_inches > length:
            rows.append(("Cut to", "%s (LH + RH)" % inches_label(length)))
        else:
            rows.append(("Length", "%s (LH + RH), no cut" % inches_label(length)))
        rows.append(("Pairs", qty_label(pairs)))

        if self.move_raw_ids:
            rows.append(("Parts", ""))
            for move in self.move_raw_ids:
                part = move.product_id.with_context(display_default_code=False).display_name
                rows.append((part, qty_label(move.product_uom_qty), "c"))
        return rows

    # --- hardware ---------------------------------------------------------------
    # Hardware rows never carry spring specs: only the kit, its drum and the lift
    # cables (owner, 2026-10-14).

    def _aa_line_notes(self):
        """The extra lines of the sale line description, e.g.
        'Track: 3" 15R | Lift: Standard | Drum: D400-144 | W 16' 0" x H 8' 0" | 650 lb'
        or 'Cables for Door 1', as (label, value) rows."""
        line = self.aa_sale_line_id
        rows = []
        for text in (line.name or "").split("\n")[1:]:
            text = text.strip()
            if not text or text.lower().startswith("kit contents"):
                continue
            for part in text.split(" | "):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("Add to Your Order:"):
                    rows.append(("Extras", part.split(":", 1)[1].strip()))
                elif re.match(r"^W [\d' \"]+x H ", part):
                    rows.append(("Door", part[2:].replace(" x H ", " x ")))
                elif re.match(r"^\d[\d,.]* lb$", part):
                    rows.append(("Weight", part))
                elif ": " in part:
                    rows.append(tuple(x.strip() for x in part.split(": ", 1)))
                else:
                    rows.append(("Note", part))
        return rows

    def _aa_kit_rows(self):
        """ONLY what goes in the hardware box (owner, 2026-10-14): the kit, every
        piece of the kit (drum included), and the lift cables ordered with it. No
        door size, track, lift or extras - those belong to other stations."""
        product = self.product_id
        qty = self.product_qty or 1.0
        rows = [("Kit", (product.product_tmpl_id.name or "").replace(" Hardware Kit", ""))]
        # No separate Drum row: the drum is already a piece in Box Contents
        # (owner, 2026-10-14).

        bom = self.env["mrp.bom"].sudo()._bom_find(product, bom_type="phantom").get(product)
        if bom:
            pieces = {}
            for line in bom.bom_line_ids:
                if line._skip_bom_line(product):
                    continue
                part = line.product_id
                pieces.setdefault(part, 0.0)
                pieces[part] += line.product_qty * qty / (bom.product_qty or 1.0)
            rows.append(("Box contents", ""))
            for part, amount in pieces.items():
                name = part.with_context(display_default_code=False).display_name
                rows.append((name, qty_label(amount), "c"))

        for cable in self.aa_cable_line_ids:
            # ONE tick for the whole cable pair (owner, 2026-10-14).
            rows.append(("Lift cable", "", "c"))
            rows += self._aa_cable_rows(cable.product_id, cable.product_uom_qty, notes=False)
        return rows

    def _aa_cable_rows(self, product=None, pairs=None, notes=True):
        """A prepared lift cable pair. The cut length comes from its kit BoM:
        the reel feet are for the PAIR, so one cable is half."""
        product = product or self.product_id
        size = re.search(r'Lift Cable (\S+)', product.product_tmpl_id.name or "")
        pairs = pairs or self.product_qty or 1.0
        rows = [("Cable", size.group(1) if size else product.display_name)]

        bom = self.env["mrp.bom"].sudo()._bom_find(product, bom_type="phantom").get(product)
        reel = bom and bom.bom_line_ids.filtered(lambda l: "reel" in (l.product_id.name or "").lower())[:1]
        if reel:
            uom = (reel.product_uom_id.name or "").lower()
            inches_per_unit = 1.0 if uom in ("in", "inch", "inches") else 12.0
            feet = reel.product_qty * inches_per_unit / 12.0
            each = feet * 12.0 / 2.0 / (bom.product_qty or 1.0)
            rows.append(("Cut", "%s x %s" % (qty_label(2 * pairs), inches_label(each))))
        else:
            rows.append(("Cut", "%s cables - length not set on the product" % qty_label(2 * pairs)))
        rows.append(("Each cable", "1 oval sleeve, 1 thimble, 1 aluminum stop"))
        for ptav in product.product_template_attribute_value_ids:
            rows.append((ptav.attribute_id.name or "For", ptav.name))
        if notes:
            rows += self._aa_line_notes()
        return rows


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_shop_spec = fields.Text(related="production_id.aa_shop_spec", string="Shop Floor Instructions")
    aa_packed = fields.Text(related="production_id.aa_packed", string="Packed Rows")
