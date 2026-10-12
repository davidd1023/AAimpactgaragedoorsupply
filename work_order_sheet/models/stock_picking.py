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

    # THE DESCRIPTION IS THE RECORD, so it is parsed rather than duplicated.
    #
    # The obvious design was a dozen new columns on sale.order.line holding the
    # specification as data. The owner does not want new columns on the
    # calculator, and there is a real argument for that: the figures already
    # exist on the line, and a second copy is a second thing that can disagree
    # with the first.
    #
    # The cost is that this reads a format rather than a field, so a change to
    # how that description is written silently empties this block. The guard is
    # that spring_engineering's own add-to-cart test asserts the shape these
    # patterns expect, by name, so the format cannot move without a test
    # failing - and a line this cannot read prints no block at all rather than
    # half of one.
    SPRING_MARKER = "custom torsion spring assembly"
    SPRING_ASSEMBLY = re.compile(r"^\s*(\w+),\s*(\d+)\s+spring", re.I)
    SPRING_ITEM = re.compile(
        r'^\s*(\w+):\s*([\d.]+)"\s*wire,\s*([\d.]+)"\s*ID,\s*([\d.]+)"\s*long',
        re.I)
    # Triple-quoted: this pattern contains both a foot mark and an inch mark.
    SPRING_DOOR = re.compile(
        r"""^\s*Door:\s*([\d,]+)\s*lb,\s*(\d+)'\s*(\d+)",\s*([\d,]+)\s*cycles""",
        re.I)

    def _work_order_inches(self, text):
        """6.0 -> 6", 32.25 -> 32.25".

        The description carries Python's float formatting, so an inside
        diameter of six arrives as "6.0". A shop sheet should read 6".
        """
        try:
            return '%g"' % float(text)
        except (TypeError, ValueError):
            return '%s"' % text

    def _work_order_spring(self, move):
        """The assembly behind this line, read off its description, or None.

        GUARDED RATHER THAN DEPENDED ON. This module prints transfers and knows
        nothing about torsion springs; it recognises the description the spring
        calculator writes and prints what it finds. It therefore works on a
        database without the calculator, with no bridge module to install.
        """
        line = move.sale_line_id if "sale_line_id" in move._fields else False
        text = (line.name or "") if line else ""
        rows = [r for r in text.splitlines() if r.strip()]

        if not rows or self.SPRING_MARKER not in rows[0].strip().lower():
            return None

        parameters = []
        springs = []

        for row in rows[1:]:
            hit = self.SPRING_ITEM.match(row)

            if hit:
                springs.append({
                    "role": hit.group(1),
                    "wire": self._work_order_inches(hit.group(2)),
                    "inside_diameter": self._work_order_inches(hit.group(3)),
                    "length": self._work_order_inches(hit.group(4)),
                })
                continue

            hit = self.SPRING_DOOR.match(row)

            if hit:
                parameters.append(("Door weight", "%s lb" % hit.group(1)))
                parameters.append(
                    ("Door height", "%s' %s\"" % (hit.group(2), hit.group(3))))
                parameters.append(("Cycle target", hit.group(4)))
                continue

            hit = self.SPRING_ASSEMBLY.match(row)

            if hit:
                parameters.insert(0, ("Springs", hit.group(2)))
                parameters.insert(0, ("Assembly", hit.group(1)))

        # A marker with nothing under it is a line this cannot read. Printing an
        # empty "SPRING ASSEMBLY" heading would say the assembly has no
        # specification, which is worse than saying nothing.
        if not springs:
            return None

        return {"parameters": parameters, "springs": springs}

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
