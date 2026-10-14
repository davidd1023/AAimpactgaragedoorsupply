import json
import math
import re

from odoo import api, fields, models

# How the shop writes the three single I.D.s and the duplex outer.
ID_LABELS = {2.625: '2 5/8"', 3.75: '3 3/4"', 5.25: '5 1/4"', 6.0: '6"'}
FILLER_ID = 5.25

# Finished stock springs: SPR-262-2.625-R
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
    # "Label|Value" rows, one per line. Read by the Shop Floor card.
    aa_shop_spec = fields.Text(
        string="Shop Floor Instructions", compute="_compute_aa_shop_spec", store=True)

    @api.depends("aa_spring_spec_json", "product_id", "product_qty")
    def _compute_aa_shop_spec(self):
        for production in self:
            rows = production._aa_spring_rows()
            production.aa_shop_spec = "\n".join("%s|%s" % row for row in rows) or False

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


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_shop_spec = fields.Text(related="production_id.aa_shop_spec", string="Shop Floor Instructions")
