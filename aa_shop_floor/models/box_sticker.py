"""THE BOX STICKER, THE OWNER'S OWN DESIGN (2026-11-27).

He drew it on the blank 4 x 6: the AA Impact logo; W/O and Order Ref large;
then Door Width, Door Height, Lift Type, High Lift on the left and Drum,
Cable Length, Cable Size, FTSC on the right; a dashed line; then Horizontal
Track and Vertical Track on the left and Spring and Turns on the right.

Every figure comes off the same reading of the order as the Hardware card
(hardware_card.py), so the sticker and the card can never disagree. A blank
is left blank, with its line, for a hand to fill in: a guess on a box label
is worse than nothing. FTSC has no figure in Odoo yet, so it is always a
line to write on.

The box's QR code stays, small, in the free corner under the spring: it is
how the box is dispatched at the counter (CLAUDE.md, "SCAN THE QR TO
DISPATCH").

Only on the 4 x 6 label. A smaller label keeps the compact layout, which was
built to shrink.
"""

import base64
import logging
import re

from odoo import models
from odoo.tools.misc import file_open

from .mrp_production import inches_label
from .hardware_card import CABLE_NAME, feet_label

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _aa_sticker_is_full_size(self):
        width, height = self._aa_sticker_inches()
        return abs(width - 4.0) < 0.05 and abs(height - 6.0) < 0.05

    def _aa_sticker_logo_src(self):
        try:
            with file_open("aa_shop_floor/static/img/aa_impact_logo.png", "rb") as fh:
                return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
        except OSError:
            return ""

    def _aa_box_sticker(self):
        """{wo, ref, width, height, lift, high_lift, drum, cable_length,
        cable_size, ftsc, horizontal, vertical, spring, turns} - '' where the
        order does not say."""
        self.ensure_one()
        data = dict.fromkeys((
            "wo", "ref", "width", "height", "lift", "high_lift", "drum",
            "cable_length", "cable_size", "ftsc", "horizontal", "vertical",
            "spring", "turns"), "")
        try:
            kit = self.aa_sale_line_id
            order = kit.order_id
            data["wo"] = self.aa_wo_number or (order and order.aa_wo_number) or ""
            if order:
                data["ref"] = self._aa_impact_wo(order.sudo()) or (order.client_order_ref or "").strip() \
                    or order.name
            if not kit:
                return data
            by_kit, _loose = self._aa_door_split(order)
            lines = by_kit.get(kit, self.env["sale.order.line"])
            notes = dict(self._aa_line_notes(kit))
            specs = self._aa_card_specs(lines)

            if kit.aa_door_width_in:
                data["width"] = feet_label(kit.aa_door_width_in)
            if kit.aa_door_height_in:
                data["height"] = feet_label(kit.aa_door_height_in)
            if not (data["width"] and data["height"]):
                door = (notes.get("Door") or "").strip()
                parts = re.split(r"\s*[xX×]\s*", door)
                if len(parts) == 2:
                    data["width"] = data["width"] or parts[0]
                    data["height"] = data["height"] or parts[1]

            drum = self._aa_card_drum(kit, specs, notes)
            lift = self._aa_card_lift(kit, notes, lines)
            data["drum"] = drum or ""
            if lift:
                hit = re.match(r"(?i)\s*high\s*lift\s*(.*)$", lift)
                if hit:
                    data["lift"] = "High Lift"
                    data["high_lift"] = hit.group(1).strip()
                else:
                    data["lift"] = lift
                    data["high_lift"] = "—" if lift == "Standard" else ""

            for line in lines:
                name = line.product_id.product_tmpl_id.name or ""
                if not CABLE_NAME.search(name):
                    continue
                size = re.search(r"Lift Cable\s+(\S+)", name, re.I)
                data["cable_size"] = size.group(1) if size else data["cable_size"]
                each = self._aa_cable_cut_inches(line.product_id)
                if each:
                    data["cable_length"] = inches_label(each)
                break

            horizontal, vertical = [], []
            for line in lines:
                if CABLE_NAME.search(line.product_id.display_name or ""):
                    continue
                facts = line.product_id._aa_track_facts()
                if not facts:
                    continue
                label = '%s" x %s' % (facts["size"], inches_label(facts["length"]))
                (vertical if facts["kind"] == "vertical" else horizontal).append(label)
            data["horizontal"] = " · ".join(horizontal)
            data["vertical"] = " · ".join(vertical)

            for label, value in self._aa_card_spring_rows(lines, specs, kit, drum, lift):
                if label.startswith("Spring") and not data["spring"]:
                    data["spring"] = value
                elif label == "Turns" and not data["turns"]:
                    data["turns"] = value.replace(" at full wind", "")
        except Exception:
            _logger.exception("Box sticker data failed for %s", self.name)
        return data
