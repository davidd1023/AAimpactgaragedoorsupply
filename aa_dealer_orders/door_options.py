"""Tracks and cables for a door, picked like the AA Calculator.

Given the door (height, lift, high lift, track type, drum, color) this returns the
prepared products to add to the order, plus notes for anything AA has to prepare
by hand (no matching prepared product).

AA Calculator lengths (inches):
    standard lift:  vertical = H - 8                 horizontal = H + 12
    high lift:      vertical = (H - 8) + (HL - 9)    horizontal = (H + 12) - (HL - 9)
Prepared tracks are picked as the shortest one that is long enough.
Prepared cable pairs come per cable size, door height (whole feet, rounded up) and
radius (12R or 15R). Cable size comes from the drum.
"""
import math
import re

# How many of each prepared track product one door takes.
# Tracks are always sold as a pair (LH + RH).
TRACK_QTY_PER_DOOR = 1
CABLE_QTY_PER_DOOR = 1  # the product is already a pair

CABLE_SIZE_BY_DRUM = {'D400-96': '1/8"', 'D400-144': '5/32"'}  # everything else 3/16"

# Trims come in 18' pieces and are sold whole. Each door takes 3 cuts at the exact
# door size, nothing added: 1 header (the width) and 2 jambs (the height). The count
# is how many 18' pieces those 3 cuts come out of (owner, 2026-10-12):
#   1 piece  if width + 2 x height <= 18'
#   2 pieces if width + height <= 18', or both jambs fit in one piece (2 x height <= 18')
#   3 pieces otherwise
# 18' is the widest door AA offers trims for; wider doors get a warning, no trims.
TRIM_COLOURS = ('White', 'Bronze', 'Black')
# The kit option's name. Shown to customers as "Plastic Trims" (owner, 2026-10-12).
TRIM_ATTRIBUTES = ('Trims', 'Plastic Trims')
TRIM_PIECE_IN = 18 * 12  # 216"


def trim_count(width, height):
    """18' trim pieces for a door of width x height (inches); None if no trims can be offered."""
    s = TRIM_PIECE_IN
    if width <= 0 or height <= 0 or width > s or height > s:
        return None
    if width + 2 * height <= s:
        return 1
    if width + height <= s or 2 * height <= s:
        return 2
    return 3


_H_RE = re.compile(r'^(\d)" Horizontal Track -\s+(\d+)" (White|Black)$')
_V_RE = re.compile(r'^(\d)" Vertical Track (\d+)" - .*\b(White|Black)$')
_C_RE = re.compile(r'^Lift Cable (\S+) Pair - Prepared \((\d+)\' Door, \d" Track \((\d+)R\)\)$')


def track_lengths(height, lift, high_lift):
    if lift == 'highlift':
        return (height - 8) + (high_lift - 9), (height + 12) - (high_lift - 9)
    return height - 8, height + 12


def cable_size(drum, lift):
    if lift == 'highlift':
        return '3/16"'
    return CABLE_SIZE_BY_DRUM.get(drum, '3/16"')


class Catalog:
    """Prepared tracks and cables found in Odoo, by their product names."""

    def __init__(self, env):
        products = env['product.product'].sudo().search([
            ('sale_ok', '=', True),
            '|', '|',
            ('name', 'ilike', 'Horizontal Track -'),
            ('name', 'ilike', 'Vertical Track'),
            ('name', 'ilike', 'Lift Cable'),
        ]) | env['product.product'].sudo().search([
            ('sale_ok', '=', True),
            ('name', 'in', [f'{c} Trims' for c in TRIM_COLOURS]),
        ])
        self.horizontal = []  # (size, length, color, product)
        self.vertical = []
        self.cables = {}      # (size, feet, radius) -> product
        self.trims = {}  # colour -> product
        for p in products.with_context(display_default_code=False):
            # Display name = template name + variant values, e.g.
            # 'Lift Cable 5/32" Pair - Prepared (8' Door, 3" Track (15R))'
            name = (p.display_name or '').strip()
            if 'RAW' in name:
                continue
            if name.endswith(' Trims') and name.split(' ')[0] in TRIM_COLOURS:
                self.trims[name.split(' ')[0]] = p
                continue
            m = _H_RE.match(name)
            if m:
                self.horizontal.append((m.group(1), int(m.group(2)), m.group(3), p))
                continue
            m = _V_RE.match(name)
            if m:
                self.vertical.append((m.group(1), int(m.group(2)), m.group(3), p))
                continue
            m = _C_RE.match(name)
            if m:
                self.cables[(m.group(1), int(m.group(2)), m.group(3))] = p

    @staticmethod
    def _shortest(items, size, color, needed):
        fits = sorted((length, p) for s, length, c, p in items
                      if s == size and c == color and length >= needed)
        return fits[0][1] if fits else None

    def door_items(self, door):
        """door: dict(width, height, lift, high_lift, track_type, drum, color, tracks, cables, trims).

        trims is the trim colour ('White', 'Bronze', 'Black') or empty for none.

        Returns (items, notes): items = [(product, qty, label)], notes = [str].
        """
        items, notes = [], []
        height = door['height']
        track = door['track_type'] or ''
        lift = door['lift']
        hl = door.get('high_lift') or 0.0
        color = door.get('color') or 'White'

        if door.get('tracks'):
            if not height:
                notes.append("Tracks: enter the door height")
            elif 'LHR' in track:
                notes.append("Tracks: LHR tracks are prepared by AA")
            else:
                size = track[:1]
                vert, horiz = track_lengths(height, lift, hl)
                h = self._shortest(self.horizontal, size, color, horiz)
                v = self._shortest(self.vertical, size, color, vert)
                if h:
                    items.append((h, TRACK_QTY_PER_DOOR, 'Tracks'))
                else:
                    notes.append(f'Tracks: no prepared {size}" horizontal for {horiz:g}" - AA prepares it')
                if v:
                    items.append((v, TRACK_QTY_PER_DOOR, 'Tracks'))
                else:
                    notes.append(f'Tracks: no prepared {size}" vertical for {vert:g}" - AA prepares it')

        if door.get('cables'):
            size = cable_size(door.get('drum'), lift)
            if not height:
                notes.append("Drum Cables: enter the door height")
            elif lift == 'highlift':
                notes.append(f"Drum Cables: high-lift {size} cables are cut by AA")
            elif 'LHR' in track:
                notes.append(f"Drum Cables: LHR {size} cables are cut by AA")
            else:
                radius = '12' if track.endswith('12R') else '15'
                feet = max(7, math.ceil(height / 12.0 - 1e-9))
                p = self.cables.get((size, feet, radius))
                if p:
                    items.append((p, CABLE_QTY_PER_DOOR, 'Cables'))
                else:
                    notes.append(f"Drum Cables: no prepared {size} pair for a {feet}' door ({radius}R) - AA cuts it")

        trim = door.get('trims')
        if trim:
            width = door.get('width') or 0.0
            if not height or not width:
                notes.append("Plastic Trims: enter the door width and height")
            elif width > TRIM_PIECE_IN:
                notes.append("Plastic Trims: not available for doors wider than 18' - no trims were added")
            elif trim not in self.trims:
                notes.append(f"Plastic Trims: no {trim} trims product found - AA will add them")
            else:
                count = trim_count(width, height)
                if count:
                    items.append((self.trims[trim], count, 'Plastic Trims'))
                else:
                    notes.append("Plastic Trims: not available for this door size - no trims were added")
        return items, notes
