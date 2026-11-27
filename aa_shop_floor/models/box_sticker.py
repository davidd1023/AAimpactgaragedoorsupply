"""THE BOX STICKER, THE OWNER'S OWN DESIGN (2026-11-27).

He drew it on the blank 4 x 6: the AA Impact logo; W/O and Order Ref large;
then Door Width, Door Height, Lift Type, High Lift on the left and Drum,
Cable Length, Cable Size, FTSC on the right; a dashed line; then Horizontal
Track and Vertical Track on the left and Spring and Turns on the right.

Every figure comes off the same reading of the order as the Hardware card
(hardware_card.py), so the sticker and the card can never disagree. A blank
is left blank, with its line, for a hand to fill in: a guess on a box label
is worse than nothing.

FTSC (Floor To Shaft Center) AND THE CABLE LENGTH ARE THE AA CALCULATOR'S OWN
FORMULA (garage-door-calculator index.html, calc(), read 2026-11-27), per
door, not the prepared cable's table - the owner: "eso no debe ser asi":

    vertical  standard  H - 8      high lift  (H - 8) + (HL - 9)
              LHR       H - 18 (3") / H - 16 (2")
    FTSC  = vertical + track offset + end bearing plate allowance
    cable = ceil(FTSC + drum allowance)          (high lift: - HL)

The table of prepared cables gives the same figure for a whole-foot door
(7' 15R: 105") and a rounded-up one for any other height, which is why the
calculation wins and the table is only the fallback.

The box's QR code stays, small, in the free corner under the spring: it is
how the box is dispatched at the counter (CLAUDE.md, "SCAN THE QR TO
DISPATCH").

Only on the 4 x 6 label. A smaller label keeps the compact layout, which was
built to shrink.
"""

import base64
import logging
import math
import re

from odoo import models
from odoo.tools.misc import file_open

from .mrp_production import inches_label
from .hardware_card import CABLE_NAME, feet_label

_logger = logging.getLogger(__name__)


# The AA calculator's constants, exactly as calc() has them.
TRACK_OFFSET = {"3-15R": 17.0, "3-LHR": 25.0, "2-LHR": 19.0, "2-12R": 13.125}
# drum -> (end bearing plate allowance, cable allowance)
DRUM_ALLOWANCE = {
    "D400-96": (3.125, 8.0), "D400-144": (3.125, 8.0),
    "D525-216": (3.125, 10.0), "5250-18": (3.125, 10.0),
    "D525-54": (3.125, 66.0), "D575-120": (4.875, 133.0), "D800-120": (4.875, 137.0),
}


def aa_calculator_ftsc_cable(height, track, lift, high_lift, drum):
    """(FTSC, cable inches) the way the AA calculator works them out, or
    (None, None) when a figure it needs is missing - never a guess."""
    if not height or track not in TRACK_OFFSET:
        return None, None
    key = next((k for k in DRUM_ALLOWANCE if drum and drum.upper().startswith(k.upper())), None)
    if not key:
        return None, None
    high_lift = high_lift or 0.0
    if lift == "highlift":
        if not high_lift:
            return None, None
        vertical = (height - 8) + (high_lift - 9)
    elif track.endswith("LHR"):
        vertical = height - 18 if track == "3-LHR" else height - 16
    else:
        vertical = height - 8
    ebf, allowance = DRUM_ALLOWANCE[key]
    ftsc = vertical + TRACK_OFFSET[track] + ebf
    cable = math.ceil(ftsc + allowance - high_lift if lift == "highlift" else ftsc + allowance)
    return ftsc, cable


def door_inches(text):
    """'120"' / '10\' 0"' / '7\'' / '84' -> inches, or 0.0 when it can't tell."""
    text = (text or "").strip()
    hit = re.match(r"""^(\d+(?:\.\d+)?)\s*'\s*(?:(\d+(?:\.\d+)?)\s*(?:"|'')?)?$""", text)
    if hit:
        return float(hit.group(1)) * 12 + float(hit.group(2) or 0)
    hit = re.match(r'^(\d+(?:\.\d+)?)\s*(?:"|in)?$', text)
    return float(hit.group(1)) if hit else 0.0


def cable_size_for(drum, lift):
    """The lift cable size the shop uses: high lift is always 3/16"; otherwise
    by drum - D400-96 1/8", D400-144 5/32", D525-216 3/16"."""
    if lift == "highlift":
        return '3/16"'
    drum = (drum or "").upper()
    for key, size in (("D400-96", '1/8"'), ("D400-144", '5/32"'), ("D525-216", '3/16"')):
        if drum.startswith(key):
            return size
    return ""


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
                each = self._aa_cable_cut_inches(line.product_id, line)
                if each and not data["cable_length"]:
                    data["cable_length"] = inches_label(each)
                break

            # THE CALCULATOR'S FTSC AND CABLE, from the door on the kit line.
            fields_ = kit._fields
            track = kit.aa_track_type if "aa_track_type" in fields_ else False
            lift_type = (kit.aa_lift_type if "aa_lift_type" in fields_ else False) \
                or ("highlift" if data["lift"] == "High Lift" else "standard")
            high = kit.aa_high_lift if "aa_high_lift" in fields_ else 0.0
            # The height is often only in the dealer's note ("120\" x 120\"").
            height = kit.aa_door_height_in or door_inches(data["height"])
            kit_drum = (kit.aa_drum if "aa_drum" in fields_ else False) or drum
            ftsc, cable = aa_calculator_ftsc_cable(height, track, lift_type, high, kit_drum)
            if not data["cable_size"]:
                data["cable_size"] = cable_size_for(kit_drum, lift_type)
            if ftsc:
                data["ftsc"] = inches_label(ftsc)
                data["cable_length"] = inches_label(cable)

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
