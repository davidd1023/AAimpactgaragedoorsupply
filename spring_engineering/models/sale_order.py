import math
import re

from odoo import _, models

# The attribute value that means "send it ready to fit". Matched on the VALUE's
# name rather than on an xml id, so the owner can attach the attribute to track
# products by hand - which is how the other product options on these pages are
# set up - without the code needing to know which products those are.
PREPARED = "prepared"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # --- what counts as a prepared vertical track -----------------------------

    def _track_prep_is_prepared(self, line):
        """True when this cart line is a vertical track ordered PREPARED."""
        values = line.product_no_variant_attribute_value_ids

        return any(
            (v.name or "").strip().lower() == PREPARED for v in values
        )

    def _track_prep_door_height_feet(self, line):
        """The door height this track is for, in FEET, or 0 if unreadable.

        READ FROM THE PRODUCT NAME, because that is where it lives: the
        products are named like "CH-VT-2-2 Vertical Track 76-7 door height
        black", and the figure before "door height" is the door height in FEET.

        Name parsing is fragile and this is the fragile part of the feature, so
        it fails LOUDLY rather than guessing: a name this cannot read adds no
        parts and tells the customer to call, instead of silently shipping the
        wrong number of brackets. If the naming ever changes, the warning says
        so on the first order rather than after fifty.
        """
        name = line.product_id.display_name or ""
        # THE FOOT MARK IS THE POINT. The live products are named
        #
        #   [CH-VT-2"] 2" Vertical Track 76" - 7' Door Height Black
        #
        # so the figure before "Door Height" carries a PRIME - 7' - and the
        # first version of this pattern allowed only "ft", "foot" and "feet".
        # It read nothing, and every prepared track came back "we could not
        # read the door height". The inch marks are why this must not simply
        # grab the first number either: 2" and 76" both appear before it.
        #
        # Accepted: 7' Door Height, 7’ Door Height, 7 ft door height, 76-7 door
        # height, and a bare "8 door height".
        hit = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:'|\u2019|ft\.?|foot|feet)?\s*[-\u2013]?\s*door\s*height",
            name,
            re.I,
        )

        if not hit:
            return 0

        feet = float(hit.group(1))

        # A plausible door is between 5 and 20 feet. Anything else means the
        # number matched is not a door height, so treat it as unreadable.
        if not 5 <= feet <= 20:
            return 0

        return feet

    # THE JAMB BRACKETS A PAIR OF VERTICAL TRACKS NEEDS, by door height.
    #
    # Taken from the owner's own garage door calculator, which carries the rule
    # as a table - andy0808al.github.io/garage-door-calculator, the JB array:
    #
    #     {min:0,   max:84,  j10:4, j12:4,  j14:4,  j16:null}
    #     {min:85,  max:96,  j10:4, j12:5,  j14:5,  j16:null}
    #     {min:97,  max:108, j10:4, j12:5,  j14:5,  j16:2}
    #     ... up to 192 inches
    #
    # ITS NUMBERS ARE PER SIDE - the card is titled "Jamb Brackets - per side"
    # and the code does `jambTotal = jambSide * 2`. The owner confirms it: "for
    # one track its 4/4/4 for a 7 foot door". A vertical track PRODUCT is the
    # L & R pair, so one of them is two tracks, and the quantities below are
    # the table DOUBLED.
    #
    # That correction matters: this previously shipped 4/4/4 for a 7 ft pair,
    # read off the same per-side display and mistaken for a whole-door figure.
    # Every prepared track since has gone out with half the brackets it needs.
    #
    # The table also reaches 16 ft, which closes the 11 and 12 ft gap that used
    # to refuse those doors - #16 climbs to 6 at 11 ft and the pattern was not
    # safe to guess from four readings. It no longer has to be guessed.
    BRACKET_MIX = (
        (0, 7, {"10": 8, "12": 8, "14": 8}),
        (8, 8, {"10": 8, "12": 10, "14": 10}),
        (9, 9, {"10": 8, "12": 10, "14": 10, "16": 4}),
        (10, 10, {"10": 8, "12": 10, "14": 10, "16": 8}),
        (11, 11, {"10": 8, "12": 10, "14": 10, "16": 12}),
        (12, 12, {"10": 8, "12": 12, "14": 12, "16": 12}),
        (13, 13, {"10": 8, "12": 12, "14": 12, "16": 16}),
        (14, 14, {"10": 8, "12": 12, "14": 16, "16": 16}),
        (15, 15, {"10": 8, "12": 12, "14": 16, "16": 20}),
        (16, 16, {"10": 8, "12": 12, "14": 20, "16": 20}),
    )

    # The catalogue part numbers, which are what the lookup keys on - a SKU is
    # a far steadier handle than a name someone may retitle.
    BRACKET_CODES = {
        "10": "ATL-610J10JBBR",
        "12": "ATL-614J12JBBR",
        "14": "ATL-616J14JBBR",
        "16": "ATL-616J16JBBR",
    }

    def _track_prep_bracket_mix(self, height_feet):
        """{size: quantity for the pair} for this door, or {} if off the table.

        Off the table means off it. #16 is still climbing at 10 ft - two more
        per foot - so continuing the pattern to 11 and 12 would be inventing a
        trade rule from four readings. An unknown height adds nothing and says
        to call.
        """
        for low, high, mix in self.BRACKET_MIX:
            if low <= height_feet <= high:
                return dict(mix)

        return {}

    def _track_prep_bracket_product(self, size, colour):
        """The jamb bracket of this size, in the track's finish.

        THE BRACKETS ARE COLOUR-MATCHED, like the flag angles. The owner stocks
        "Jamb Bracket # 10 Black" and "Jamb Bracket # 10 White" - eight
        products, four per finish - and only four of them belong on any given
        track.

        An earlier version searched only the catalogue part numbers and the
        "J-10 Jamb Bracket" names that come from garage_door_supply's data. The
        live site has neither, so every prepared track was refused with a list
        of three part numbers that exist nowhere. The finish-matched name is
        tried FIRST because that is what the live site actually has; the part
        numbers remain for a database carrying the catalogue data instead.
        """
        Product = self.env["product.product"].sudo()

        # As the owner names them, and the same without the space after the
        # hash - the obvious way for someone to type it next time.
        for pattern in ("Jamb Bracket # %s %s", "Jamb Bracket #%s %s"):
            found = Product.search(
                [("name", "=ilike", pattern % (size, colour))], limit=1
            )

            if found:
                return found

        code = self.BRACKET_CODES.get(size)

        if code:
            found = Product.search([("default_code", "=", code)], limit=1)

            if found:
                return found

        return Product.search(
            [("name", "=ilike", "J-%s Jamb Bracket" % size)], limit=1
        )

    def _track_prep_bracket_name(self, size, colour):
        """What the lookup wanted, phrased so a person can search for it."""
        return "Jamb Bracket # %s %s" % (size, colour)

    # One at each top corner, so two for the pair. The owner's own kit
    # configurator returns "2 flag angles" for a 9' x 7' door, which is the
    # same answer from the other direction.
    FLAG_ANGLES_PER_DOOR = 2

    # The finishes a track and its flag angle come in. Matched as whole words so
    # a track that merely mentions a colour elsewhere in its name is not caught.
    COLOURS = ("Black", "White")

    def _track_prep_colour(self, line):
        """The track's finish, as the flag angle products spell it, or None.

        The flag angle has to MATCH THE TRACK: the products are "Flag Angle
        Black" and "Flag Angle White", so a black track must not ship a white
        angle. There is no sensible default here - shipping the wrong colour is
        a return - so an unrecognised finish adds nothing and says so, the same
        as an unreadable height.
        """
        name = line.product_id.display_name or ""

        for colour in self.COLOURS:
            if re.search(r"\b%s\b" % colour, name, re.I):
                return colour

        return None

    def _track_prep_configured_part(self, key):
        """The product named in the settings for this role, or an empty set."""
        ref = self.env["ir.config_parameter"].sudo().get_param(
            "spring_engineering.track_prep_%s_product_id" % key
        )

        if not ref:
            return self.env["product.product"]

        try:
            return self.env["product.product"].sudo().browse(int(ref)).exists()
        except (TypeError, ValueError):
            return self.env["product.product"]

    def _track_prep_flag_product(self, line):
        """The flag angle in the track's own finish.

        Looked up BY NAME rather than configured, because there is one per
        colour and the right one depends on the track rather than on a setting.
        The setting stays as a fallback for a track whose finish is a colour
        these products do not cover.
        """
        colour = self._track_prep_colour(line)

        if colour:
            found = self.env["product.product"].sudo().search(
                [("name", "=ilike", "Flag Angle %s" % colour)], limit=1
            )

            if found:
                return found

        return self._track_prep_configured_part("flag")

    # --- keeping the parts in step with the track -----------------------------

    def _track_prep_sync(self, line):
        """Create, update or remove the parts belonging to one track line."""
        self.ensure_one()

        existing = self.order_line.filtered(lambda l: l.track_prep_parent_id == line)

        if not line.exists() or not self._track_prep_is_prepared(line):
            existing.unlink()
            return None

        height_feet = self._track_prep_door_height_feet(line)

        if not height_feet:
            existing.unlink()
            return _(
                "We could not read the door height from “%s”, so the jamb"
                " brackets and flag angle were not added. Please call us and we"
                " will prepare it for you.",
                line.product_id.display_name,
            )

        colour = self._track_prep_colour(line)

        if not colour:
            existing.unlink()

            return _(
                "We could not tell what finish “%s” is, so the flag angle was"
                " not added - it has to match the track. Please call us and we"
                " will prepare it for you.",
                line.product_id.display_name,
            )

        mix = self._track_prep_bracket_mix(height_feet)

        if not mix:
            existing.unlink()

            return _(
                "A %s ft door is outside the sizes we prepare tracks for, so"
                " the parts were not added. Please call us and we will prepare"
                " it for you.",
                ("%g" % height_feet),
            )

        wanted = {
            "flag": (
                self._track_prep_flag_product(line),
                self.FLAG_ANGLES_PER_DOOR * line.product_uom_qty,
            ),
        }

        for size, qty in mix.items():
            wanted["jamb_%s" % size] = (
                self._track_prep_bracket_product(size, colour),
                qty * line.product_uom_qty,
            )

        missing = [k for k, (p, _q) in wanted.items() if not p]

        if missing:
            existing.unlink()

            # NAME WHAT IS MISSING, THE WAY THE OWNER NAMES IT. The first
            # version of this said "the parts are not configured yet", which
            # sent someone looking for a setting that does not exist. The
            # second named the catalogue PART NUMBERS - better, but they were
            # the numbers from a module the live site does not have, so the
            # message listed three codes that exist nowhere. A product name is
            # something that can actually be searched for in the back end.
            wants = ", ".join(sorted(
                self._track_prep_bracket_name(key.replace("jamb_", ""), colour)
                if key.startswith("jamb_")
                else "Flag Angle %s" % colour
                for key in missing
            ))

            return _(
                "We are missing a part needed to prepare this track (%s), so it"
                " was not added. Please call us and we will prepare it for you.",
                wants,
            )

        for role, (product, qty) in wanted.items():
            part = existing.filtered(lambda l: l.track_prep_role == role)[:1]

            if part:
                if part.product_uom_qty != qty:
                    part.product_uom_qty = qty
                continue

            self.env["sale.order.line"].create({
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "track_prep_parent_id": line.id,
                "track_prep_role": role,
            })

        # Anything linked to this track that is no longer one of the two roles -
        # left over from an earlier version of this rule - goes.
        existing.filtered(lambda l: l.track_prep_role not in wanted).unlink()

        return None

    # --- hooks ----------------------------------------------------------------

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        """Add a track, then add what preparing it needs."""
        result = super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)
        line = self.env["sale.order.line"].browse(result.get("line_id"))

        if line.exists():
            warning = self._track_prep_sync(line)

            if warning:
                result["warning"] = "\n".join(filter(None, [result.get("warning"), warning]))

        return result

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        """Follow the track's quantity, and never let a part be edited alone.

        A customer who sets the track to 3 gets three doors' worth of brackets.
        A customer who edits the BRACKET line directly is redirected to the
        track, because a prepared track with the wrong number of brackets is
        not a thing the owner sells - and silently accepting the edit would
        ship exactly that.
        """
        line = self.env["sale.order.line"].browse(line_id)

        if line.exists() and line.track_prep_parent_id:
            parent = line.track_prep_parent_id

            if quantity <= 0:
                # Removing a part means the track is no longer prepared.
                return super()._cart_update_line_quantity(parent.id, 0, **kwargs)

            self._track_prep_sync(parent)

            return {"quantity": line.product_uom_qty, "line_id": line.id}

        result = super()._cart_update_line_quantity(line_id, quantity, **kwargs)

        if line.exists():
            self._track_prep_sync(line)

        return result
