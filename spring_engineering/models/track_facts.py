"""READING A TRACK, WHETHER ITS FACTS ARE IN ITS NAME OR IN ITS VARIANT.

Three separate pieces of code take a prepared track apart to find its size,
its length, its door height and its finish, and all three do it with an
anchored regex over the product's name:

    aa_dealer_orders/door_options.py   the dealer Quick Order's catalogue
    aa_shop_floor/models/mrp_production.py   the bench card - and its CUT
    aa_dealer_orders/kit_setup.py      refreshing prepared track costs

    ^(\\d)" Horizontal Track -\\s+(\\d+)" (White|Black)$

Folding the tracks into one product per size and type (owner, 2026-10-23:
"they should be separated by 3" and 2", and also track type so horizontal and
vertical") moves the length and the finish OUT of that name and into variant
values, and every one of those patterns stops matching. The shop floor one is
why this is written carefully rather than quickly: the length it reads is the
length a bench CUTS TO.

SO THE FACTS ARE READ FROM THE WHOLE OF WHAT A VARIANT SAYS - its name with
its chosen values on the end (_aa_choice_text) - with patterns loose enough
not to care how that text is punctuated. Before the merge that text is the
old name, double spaces and all; after it, the same words in a different
order. One reader, both shapes, which is what lets this ship before the
catalogue is merged and keep working after.

A RAW TRACK IS NOT A PREPARED TRACK. The raw stock is a different product
that stays as it is (owner, 2026-10-23: "Leave RAW alone"), and reading one as
a prepared track would put a 9'6" cut on a bench card. It is refused outright.
"""

import re

from odoo import models

# The size is the first thing a track says: 2" or 3".
_SIZE = re.compile(r'^\s*(?:\[[^\]]*\]\s*)?(\d)\s*"')

# A length in inches: two or three digits, so the leading 2" or 3" cannot be
# mistaken for one.
_INCHES = re.compile(r'(?<!\d)(\d{2,3})\s*"')

# The door height a vertical track is for, in feet.
_FEET = re.compile(r"(?<!\d)(\d{1,2})\s*'")

_COLOUR = re.compile(r"\b(White|Black|Galvanized|Galvanised)\b", re.I)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _aa_track_facts(self):
        """{kind, size, length, door, colour} for a prepared track, or None.

        kind    "horizontal" or "vertical"
        size    "2" or "3", as a string, the way every caller prints it
        length  inches, as a float - what a bench cuts to
        door    the door height in feet for a vertical track, else None
        colour  "White" or "Black", spelled as the catalogue spells it
        """
        self.ensure_one()
        text = " ".join((self._aa_choice_text() or "").split())

        if not text or re.search(r"\bRAW\b", text, re.I):
            return None

        horizontal = re.search(r"\bHorizontal\s+Track\b", text, re.I)
        vertical = re.search(r"\bVertical\s+Track\b", text, re.I)

        if not (horizontal or vertical):
            return None

        size = _SIZE.search(text)
        colour = _COLOUR.search(text)

        # THE LENGTH IS THE INCHES THAT IS NOT THE SIZE, which is what the
        # two-to-three digit pattern says. A vertical track states its own
        # length and the door height it is for - 76" for a 7' door - and the
        # inches are the track.
        inches = _INCHES.search(text)
        feet = _FEET.search(text) if vertical else None

        if not (size and colour and inches):
            return None

        return {
            "kind": "vertical" if vertical else "horizontal",
            "size": size.group(1),
            "length": float(inches.group(1)),
            "door": int(feet.group(1)) if feet else None,
            "colour": colour.group(1).title(),
        }
