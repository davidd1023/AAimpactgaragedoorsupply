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
        # "... 76-7 door height ..." -> the 7, in feet.
        hit = re.search(r"(\d+(?:\.\d+)?)\s*(?:ft\.?|foot|feet)?\s*door\s*height", name, re.I)

        if not hit:
            return 0

        feet = float(hit.group(1))

        # A plausible door is between 5 and 20 feet. Anything else means the
        # number matched is not a door height, so treat it as unreadable.
        if not 5 <= feet <= 20:
            return 0

        return feet

    # JAMB BRACKETS PER SIDE, by door height, from the owner:
    #
    #   4-Section / 6-to-7-foot door   6 total, 3 per side
    #   5-Section / 8-to-9-foot door   8 total, 4 per side
    #   6-Section / 10-to-12-foot door 10 total, 5 per side
    #
    # A TABLE, NOT A FORMULA. "One per 24 inches, rounded up" was the first
    # rule tried here and it is wrong: it gives four brackets for a 7 ft door
    # where the trade fits three, and it would have shipped a spare on every
    # residential order. The bands do not divide evenly either - 6 and 7 feet
    # share a count, so do 8 and 9, and then three heights share the next - so
    # there is no spacing that reproduces them. Written down as the owner gave
    # it, bounds inclusive, in feet.
    BRACKETS_PER_SIDE = (
        (6, 7, 3),
        (8, 9, 4),
        (10, 12, 5),
    )

    def _track_prep_bracket_count(self, height_feet):
        """Jamb brackets for ONE vertical track, or 0 if the height is off the
        table.

        Off the table means off it: a 14 ft door is not in the bands the owner
        gave, and extrapolating the pattern would be inventing a trade rule.
        It adds nothing and says to call, which is the same answer this gives
        for a height it cannot read at all.
        """
        for low, high, count in self.BRACKETS_PER_SIDE:
            if low <= height_feet <= high:
                return count

        return 0

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
            "garage_door_supply.track_prep_%s_product_id" % key
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

    def _track_prep_jamb_product(self, line):
        """The jamb bracket for this track.

        THE SIZE DEPENDS ON THE TRACK and the mapping is not yet recorded -
        there are four in the catalogue, J-10 to J-16, at four prices. Until it
        is, this is the single configured bracket, which is right for a shop
        that stocks one size and wrong the moment it stocks two. The mapping
        belongs here and nowhere else.
        """
        return self._track_prep_configured_part("jamb")

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

        if not self._track_prep_colour(line):
            existing.unlink()

            return _(
                "We could not tell what finish “%s” is, so the flag angle was"
                " not added - it has to match the track. Please call us and we"
                " will prepare it for you.",
                line.product_id.display_name,
            )

        brackets = self._track_prep_bracket_count(height_feet)

        if not brackets:
            existing.unlink()

            return _(
                "A %s ft door is outside the sizes we prepare tracks for, so"
                " the parts were not added. Please call us and we will prepare"
                " it for you.",
                ("%g" % height_feet),
            )

        wanted = {
            "jamb": (self._track_prep_jamb_product(line), brackets * line.product_uom_qty),
            "flag": (self._track_prep_flag_product(line), 1 * line.product_uom_qty),
        }
        missing = [k for k, (p, _q) in wanted.items() if not p]

        if missing:
            existing.unlink()
            return _(
                "The track preparation parts are not configured yet, so they"
                " were not added. Please call us and we will prepare it for you."
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
