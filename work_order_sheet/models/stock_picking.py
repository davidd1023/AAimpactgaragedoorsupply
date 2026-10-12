import re

from odoo import models

# WHAT A LENGTH LOOKS LIKE IN A PRODUCT NAME. The catalogue writes a track as
#
#   [CH-VT-2"] 2" Vertical Track 76" - 7' Door Height Black
#
# where 2" is the track PROFILE, 76" is the length to cut and 7' is the door it
# suits. Three measurements in one name, and only the middle one is the length,
# which is why this anchors on the words "Vertical Track" or "Horizontal Track"
# rather than taking the first number it meets.
TRACK_LENGTH = re.compile(
    r"(?:vertical|horizontal)\s+track\s+(\d+(?:\s+\d+/\d+)?|\d+/\d+)\s*[\"”]?",
    re.I,
)

# A cable's length, for a catalogue that ever carries cut cables. A reel is not
# a length and must not be read as one - "500ft Reel" is a quantity of stock.
CABLE_LENGTH = re.compile(
    r"cable\s+(\d+(?:\s+\d+/\d+)?)\s*[\"”]", re.I)

KINDS = (
    ("track", re.compile(r"\btrack\b", re.I)),
    ("cable", re.compile(r"\bcable\b", re.I)),
)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _work_order_kind(self, name):
        """track, cable, or nothing in particular."""
        for kind, pattern in KINDS:
            if pattern.search(name or ""):
                return kind

        return ""

    def _work_order_length(self, name):
        """The length to cut, as the name writes it, or "".

        READ, NOT COMPUTED. Everything the old papers printed - drum, EBF, the
        floor-to-shaft figure, the bracket mix - came from the door calculator
        working out a door. A website order has no door behind it, only
        products, so the only length that honestly belongs on this sheet is the
        one the product itself names.
        """
        name = name or ""
        hit = TRACK_LENGTH.search(name)

        if not hit and "reel" not in name.lower():
            hit = CABLE_LENGTH.search(name)

        if not hit:
            return ""

        return '%s"' % hit.group(1).strip()

    def _work_order_spring(self, move):
        """The spring parameters behind this line, or None.

        GUARDED RATHER THAN DEPENDED ON. This module prints transfers and knows
        nothing about torsion springs; spring_engineering owns those numbers and
        writes them on the sale line. Checking that the field exists keeps the
        two apart - the sheet works on a database without the calculator, and
        gains the detail on one that has it, with no third module to install
        and no load order to get right.
        """
        line = move.sale_line_id if "sale_line_id" in move._fields else False

        if not line or "spring_assembly" not in line._fields:
            return None

        if not line.spring_assembly:
            return None

        return {
            "parameters": line.spring_parameter_rows(),
            "springs": line.spring_detail_rows(),
        }

    def _work_order_lines(self):
        """Every product on this work order, in the order it appears.

        EVERY product, not only the ones this module understands. A sheet that
        silently drops the drum because it is neither a track nor a cable sends
        somebody to the shelf for half an order.
        """
        self.ensure_one()
        lines = []

        for move in self.move_ids:
            product = move.product_id
            name = product.display_name or ""
            lines.append({
                "code": product.default_code or "",
                "name": product.name or name,
                "quantity": move.product_uom_qty,
                "uom": move.product_uom.name or "",
                "kind": self._work_order_kind(name),
                "length": self._work_order_length(name),
                "spring": self._work_order_spring(move),
            })

        return lines
