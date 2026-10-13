import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .work_station import DISPATCH, MAKERS, STATIONS

# WHAT A LENGTH LOOKS LIKE IN A PRODUCT NAME. The catalogue writes a track as
#
#   [CH-VT-2"] 2" Vertical Track 76" - 7' Door Height Black
#
# where 2" is the track PROFILE, 76" is the length to cut and 7' is the door it
# suits. Three measurements in one name, and only the middle one is the length,
# which is why this anchors on the words "Vertical Track" or "Horizontal Track"
# rather than taking the first number it meets.
# EVERY NUMBER IN THE NAME, so the length can be picked out of any of them.
# The anchored pattern this replaces required the measurement to sit directly
# after the words "Vertical Track" or "Horizontal Track", which held for the
# vertical names and not for the horizontal ones - they lost their length
# entirely, with no sign on the sheet that anything was missing.
NAME_NUMBER = re.compile(r"(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)")

# A track length in inches, bounded so the other numbers in a name cannot be
# mistaken for one: the profile (2" or 3"), the door height in feet (7, 9, 10)
# and anything inside a part code all fall outside it.
TRACK_LENGTH_RANGE = (12.0, 300.0)

# A cable's length, for a catalogue that ever carries cut cables. A reel is not
# a length and must not be read as one - "500ft Reel" is a quantity of stock.
CABLE_LENGTH = re.compile(r"cable\s+(\d+(?:\s+\d+/\d+)?)\s*[\"”]", re.I)

# WHAT A CABLE IS CALLED IN THIS CATALOGUE, which is mostly not "cable".
# The reel is "1/8" 7X19 GAC (500 FT REEL)" - GAC is galvanized aircraft cable
# - and its fittings are a sleeve and a thimble. Matching only the word cable
# recognised none of them, so they fell through to their eCommerce category,
# which is Tracks, and printed on the tracks page.
# CABLE IS TESTED BEFORE TRACK, and the order is the point. A cable is often
# named for the track or door it suits - "1/8\" Lift Cable for 2in Track" -
# while a track is never named for a cable. Testing track first read every one
# of those as a track and printed it on the wrong page, which no amount of
# widening the cable pattern could fix.
KINDS = (
    ("cable", re.compile(
        r"\bcable\b|\bgac\b|\b7\s*x\s*19\b|\bthimble\b"
        r"|\boval\s+sleeve\b|\baircraft\b", re.I)),
    ("track", re.compile(r"\btrack\b", re.I)),
)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # --- reading a product name ----------------------------------------------

    def _work_order_kind(self, name):
        """track, cable, or nothing in particular."""
        for kind, pattern in KINDS:
            if pattern.search(name or ""):
                return kind

        return ""

    def _work_order_length(self, name):
        """The length to cut, as the name writes it, or "".

        READ, NOT COMPUTED. A website order has no door behind it, only
        products, so the only length that honestly belongs on this sheet is the
        one the product itself names.
        """
        name = name or ""

        if self._work_order_kind(name) == "track":
            return self._work_order_track_length(name)

        if "reel" not in name.lower():
            hit = CABLE_LENGTH.search(name)

            if hit:
                return self._work_order_inches(
                    hit.group(1).strip().replace(" ", ""))

        return ""

    def _work_order_track_length(self, name):
        """The longest plausible measurement in a track's name.

        A TRACK NAME CARRIES SEVERAL NUMBERS and the length is the big one:

            [CH-VT-2"] 2" Vertical Track 76" - 7' Door Height Black

        2" is the profile, 7' is the door, 76" is what gets cut. Taking the
        number that FOLLOWS the words "Vertical Track" worked for these and
        silently failed on the horizontal names, whose wording differs - they
        printed no length at all, and a blank column looks like a product that
        has none rather than a rule that missed.

        So every number is read and the ones that could be a track are kept,
        which no profile and no door height can be.
        """
        low, high = TRACK_LENGTH_RANGE
        best = 0.0

        for text in NAME_NUMBER.findall(name):
            value = self._work_order_number(text)

            if value is not None and low <= value <= high:
                best = max(best, value)

        return self._work_order_inches(best) if best else ""

    def _work_order_number(self, text):
        """"76", "76 1/2" or "17.5" as a float, or None."""
        text = (text or "").strip()

        try:
            if " " in text:
                whole, fraction = text.split(" ", 1)
                top, bottom = fraction.split("/")

                return float(whole) + float(top) / float(bottom)

            if "/" in text:
                top, bottom = text.split("/")

                return float(top) / float(bottom)

            return float(text)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def _work_order_inches(self, text, fraction=True):
        """32.25 -> 32 1/4", 6.0 -> 6", 0.2625 -> 0.2625".

        IN EIGHTHS, BECAUSE THAT IS WHAT A TAPE MEASURE READS. A length of
        32.25" is correct and useless at a bench; the trade writes it 32 1/4",
        and this project's own notes write inside diameters the same way -
        3 3/4" inside 6", never 3.75.

        WIRE IS THE EXCEPTION and passes fraction=False. A wire size is a
        decimal gauge, not a measurement off a tape: 0.2625" snapped to the
        nearest eighth would read 1/4", which is a different wire.
        """
        try:
            value = float(text)
        except (TypeError, ValueError):
            return '%s"' % text

        if not fraction:
            return '%g"' % value

        whole = int(value)
        eighths = int(round((value - whole) * 8))

        if eighths == 8:
            whole += 1
            eighths = 0

        if not eighths:
            return '%d"' % whole

        numerator, denominator = eighths, 8

        while numerator % 2 == 0:
            numerator //= 2
            denominator //= 2

        return '%d %d/%d"' % (whole, numerator, denominator)

    # --- the spring assembly, read off its description ------------------------
    #
    # The owner does not want extra columns on the calculator, and the figures
    # already exist on the line. The cost is that this reads a FORMAT, so
    # spring_engineering's own add-to-cart test asserts the shape these
    # patterns expect, by name.
    SPRING_MARKER = "custom torsion spring assembly"
    SPRING_ASSEMBLY = re.compile(r"^\s*(\w+),\s*(\d+)\s+spring", re.I)
    SPRING_ITEM = re.compile(
        r'^\s*(\w+):\s*([\d.]+)"\s*wire,\s*([\d.]+)"\s*ID,\s*([\d.]+)"\s*long',
        re.I)
    # EACH FACT ON ITS OWN, not the line as a whole. The door line gained a
    # width and a hi-lift, and an order placed before they existed has neither
    # - matching the whole line would print nothing for those rather than
    # printing what they do have.
    SPRING_DOOR = re.compile(r"^\s*Door:", re.I)
    DOOR_WIDE = re.compile(r"""(\d+)'\s*(\d+)"\s*wide""", re.I)
    DOOR_HIGH = re.compile(r"""(\d+)'\s*(\d+)"\s*high""", re.I)
    # The trailing inch mark is appended rather than written inside the
    # string: a raw literal ending in a quote cannot close cleanly.
    DOOR_FEET = re.compile(r"(\d+)'\s*(\d+)" + '"')
    DOOR_WEIGHT = re.compile(r"([\d,]+)\s*lb", re.I)
    DOOR_HILIFT = re.compile(r"""([\d.]+)"\s*hi-?lift""", re.I)
    DOOR_CYCLES = re.compile(r"([\d,]+)\s*cycles", re.I)

    def _work_order_sale_order(self):
        """The order this transfer is for, however it is attached to it.

        A TRANSFER DOES NOT ALWAYS CARRY THE LINK. When it is created straight
        from a sale order it has sale_id and its moves have sale_line_id, and
        everything here reads those. When it is made by a route or by hand it
        has only the Source Document - the plain text "S00003" in the corner of
        the form - and all of it came back empty: no springs, no door, no
        specification, because every one of those is written on an order line
        this could not reach.
        """
        if "sale_id" in self._fields and self.sale_id:
            return self.sale_id

        origin = (self.origin or "").strip()

        if not origin:
            return self.env["sale.order"].browse()

        # An origin can carry more than the order name, so the first word is
        # tried as well as the whole of it.
        for candidate in (origin, origin.split()[0], origin.split(",")[0]):
            found = self.env["sale.order"].search(
                [("name", "=", candidate.strip())], limit=1)

            if found:
                return found

        return self.env["sale.order"].browse()

    def _work_order_order_line(self, move):
        """The order line behind a move, by link or by product."""
        if "sale_line_id" in move._fields and move.sale_line_id:
            return move.sale_line_id

        order = self._work_order_sale_order()

        if not order:
            return self.env["sale.order.line"].browse()

        return order.order_line.filtered(
            lambda l: l.product_id == move.product_id and not l.display_type)[:1]

    def _work_order_spring(self, move):
        """The assembly behind this line, read off its description, or None.

        GUARDED RATHER THAN DEPENDED ON. This module prints transfers and knows
        nothing about torsion springs; it recognises the description the spring
        calculator writes and prints what it finds, so it works on a database
        without the calculator and needs no bridge module.
        """
        line = self._work_order_order_line(move)

        return self._work_order_spring_from_text((line.name or "") if line else "")

    def _work_order_spring_from_text(self, text):
        """The assembly a description carries, or None."""
        rows = [r for r in (text or "").splitlines() if r.strip()]

        # THE MARKER IN THE FIRST FEW ROWS, not strictly the first. A spring
        # added as a kit option is described the same way but can carry a line
        # above it, and a spring that is not recognised prints as a bare line
        # with no specification at all.
        if not any(self.SPRING_MARKER in row.strip().lower() for row in rows[:3]):
            return None

        parameters = []
        springs = []
        door = {}

        for row in rows[1:]:
            hit = self.SPRING_ITEM.match(row)

            if hit:
                springs.append({
                    "role": hit.group(1),
                    "wire": self._work_order_inches(hit.group(2), fraction=False),
                    "inside_diameter": self._work_order_inches(hit.group(3)),
                    "length": self._work_order_inches(hit.group(4)),
                })
                continue

            if self.SPRING_DOOR.match(row):
                door = self._work_order_door_facts(row)
                continue

            hit = self.SPRING_ASSEMBLY.match(row)

            if hit:
                parameters.insert(0, ("Springs", hit.group(2)))
                parameters.insert(0, ("Assembly", hit.group(1)))

        # A marker with nothing under it is a line this cannot read. An empty
        # "SPRING ASSEMBLY" heading would say the assembly has no
        # specification, which is worse than saying nothing.
        if not springs:
            return None

        # Only what the customer actually gave. A door with no hi-lift says
        # nothing about hi-lift rather than printing a zero somebody has to
        # decide the meaning of.
        for label, key in (("Door width", "width"), ("Door height", "height"),
                           ("Door weight", "weight"), ("Hi-lift", "hilift"),
                           ("Cycle target", "cycles")):
            if door.get(key):
                parameters.append((label, door[key]))

        return {"parameters": parameters, "springs": springs, "door": door}

    def _work_order_door_facts(self, row):
        """The door line read fact by fact: width, height, weight, hi-lift."""
        facts = {}
        wide = self.DOOR_WIDE.search(row)
        high = self.DOOR_HIGH.search(row)

        if wide:
            facts["width"] = "%s' %s\"" % (wide.group(1), wide.group(2))

        if high:
            facts["height"] = "%s' %s\"" % (high.group(1), high.group(2))
        else:
            # The older line carried one foot-and-inch figure and it was the
            # height, so a sheet printed from an old order still says so.
            plain = [m for m in self.DOOR_FEET.finditer(row)
                     if not wide or m.start() != wide.start()]

            if plain:
                facts["height"] = "%s' %s\"" % (plain[0].group(1),
                                                 plain[0].group(2))

        weight = self.DOOR_WEIGHT.search(row)

        if weight:
            facts["weight"] = "%s lb" % weight.group(1)

        hilift = self.DOOR_HILIFT.search(row)

        if hilift:
            facts["hilift"] = '%s"' % hilift.group(1)

        cycles = self.DOOR_CYCLES.search(row)

        if cycles:
            facts["cycles"] = cycles.group(1)

        return facts

    # HOW A DEALER KIT ORDER WRITES THE DOOR. aa_dealer_orders appends a line
    # to the kit's own description:
    #
    #   Track: 3" 15R | Lift: High Lift 12" | Drum: D400-96 | W 9' x H 7' | 300 lb
    #
    # A different shape from the spring calculator's, and the only record of a
    # door on an order that has no spring on it.
    # EACH ONE ON ITS OWN. The dealer form writes "W 9' 0\" x H 7' 0\"" when it
    # has both and "W 9' 0\"" when it has only one, so a pattern that required
    # the pair found nothing whenever a customer gave one of them.
    DEALER_WIDTH = re.compile(r"\bW\s+([^|]*?)\s*(?:x\s*H\b|\||$)", re.I)
    DEALER_HEIGHT = re.compile(r"\bH\s+([^|]*?)\s*(?:\||$)", re.I)
    # The trailing inch mark is appended, as above: a raw literal cannot end
    # in a quote.
    DEALER_HILIFT = re.compile(
        r"(?:high\s*lift|hi-?lift)\s*([\d.]+)\s*" + '"', re.I)

    # The dealer note is recognisable, and a weight found anywhere else is not
    # the door's. A spring warning is prose - it repeats door weights and drum
    # ratings - and it is written AFTER the door, so it is cut off entirely
    # rather than searched.
    DEALER_MARK = re.compile(r"\b(?:Track|Lift|Drum)\s*:", re.I)
    SPRING_WARNING = re.compile(r"SPRING\s+WARNING", re.I)

    # A WEIGHT THAT IS A RATING IS NOT A DOOR.
    #
    # THE 530 lb BUG, and it was never the door at all. The kit's Drum option
    # is labelled with what the drum can carry - "D400-96 (up to 530 lb)",
    # "D575-120 (high lift up to 120", up to 1,000 lb)" - and Odoo lists the
    # chosen options in the order line's description, above the door note. The
    # first weight in that text won, so a 355 lb door printed as 530 lb: the
    # drum's rating, read off the drum's own name.
    #
    # Both places such a figure can hide are removed before the weight is
    # read, and either would do on its own: the Drum segment, and anything in
    # brackets. The door note writes neither - "Drum: D400-96" carries the code
    # alone and the weight is never bracketed - so nothing real is lost.
    DRUM_SEGMENT = re.compile(r"(?:^|\|)\s*Drum\s*:[^|\n]*", re.I | re.M)
    BRACKETED = re.compile(r"\([^)]*\)")

    def _work_order_door_weight(self, text):
        """The door's own weight in a note, ignoring anything's rating."""
        text = self.BRACKETED.sub(" ", self.DRUM_SEGMENT.sub(" ", text or ""))
        hit = self.DOOR_WEIGHT.search(text)

        return ("%s lb" % hit.group(1)) if hit else ""

    def _work_order_dealer_door(self, text):
        """The door facts a dealer kit order carries, or {}."""
        facts = {}
        text = text or ""
        warning = self.SPRING_WARNING.search(text)

        if warning:
            text = text[:warning.start()]

        # Only from a line that IS a dealer note. Any other line that happens
        # to carry a figure in pounds - a drum rating, a note about capacity -
        # would otherwise be read as the door's weight.
        #
        # THE PIPE IS ENOUGH ON ITS OWN. Requiring Track:, Lift: or Drum: was
        # too strict: a kit ordered without a track or a lift has none of them,
        # and its note is just a size and a weight joined by pipes. That change
        # took the weight off those sheets instead of correcting it, which is
        # the opposite of the fix it was meant to be. A product description
        # does not contain " | ", so the join is a good enough signal.
        if not (self.DEALER_MARK.search(text)
                or self.DEALER_WIDTH.search(text)
                or self.DEALER_HEIGHT.search(text)
                or " | " in text):
            return {}
        width = self.DEALER_WIDTH.search(text)
        height = self.DEALER_HEIGHT.search(text)

        if width and width.group(1).strip():
            facts["width"] = width.group(1).strip()

        if height and height.group(1).strip():
            facts["height"] = height.group(1).strip()

        weight = self._work_order_door_weight(text)

        if weight:
            facts["weight"] = weight

        hilift = self.DEALER_HILIFT.search(text)

        if hilift:
            facts["hilift"] = '%s"' % hilift.group(1)

        return facts

    def _work_order_feet(self, inches):
        """108 -> 9' 0", for a figure that was collected in inches."""
        if not inches:
            return ""

        feet, over = divmod(int(round(float(inches))), 12)

        return "%d' %d\"" % (feet, over)

    def _work_order_stored_door(self, line):
        """The door RECORDED on an order line, as the fields hold it, or {}.

        PREFERRED OVER EVERY READING OF THE DESCRIPTION, because this is the
        figure the customer typed rather than something that looked like it in
        a sentence. The fields belong to spring_engineering, so their absence
        is normal and means only that this database has no calculator - the
        prose is still read for an order placed before they existed.
        """
        if not line or "aa_door_weight_lb" not in line._fields:
            return {}

        facts = {}
        width = self._work_order_feet(line.aa_door_width_in)
        height = self._work_order_feet(line.aa_door_height_in)

        if width:
            facts["width"] = width

        if height:
            facts["height"] = height

        if line.aa_door_weight_lb:
            facts["weight"] = "%g lb" % line.aa_door_weight_lb

        if line.aa_door_hi_lift_in:
            facts["hilift"] = '%g"' % line.aa_door_hi_lift_in

        if line.aa_door_cycles:
            facts["cycles"] = line.aa_door_cycles

        return facts

    def _work_order_door_lines(self):
        """Every order line that could describe the door, once each."""
        self.ensure_one()
        lines = self.env["sale.order.line"].browse()

        for move in self.move_ids:
            lines |= self._work_order_order_line(move)

        # AND THE ORDER'S OWN LINES, for a door written on something that is
        # not on this transfer at all - a spring that moves no stock, or a kit
        # line whose move is on another step of the route.
        order = self._work_order_sale_order()

        if order:
            lines |= order.order_line.filtered(lambda l: not l.display_type)

        return lines

    def _work_order_door(self):
        """The door this whole order is for, if anything on it says.

        Taken from the spring assembly, which is the only thing a website order
        carries that describes a door. Printed on EVERY page, because a track
        cutter holding the tracks page is cutting for that same door.
        """
        self.ensure_one()
        order_lines = self._work_order_door_lines()

        # WHAT WAS STORED, FIRST. Both the calculator and the kit page record
        # the door as numbers on the line they create, and a number cannot be
        # misread. The fullest record wins, so a kit line carrying a size and a
        # weight beats a spring line carrying only what the price needed.
        best = {}

        for line in order_lines:
            facts = self._work_order_stored_door(line)

            if len(facts) > len(best):
                best = facts

        if best:
            return best

        for line in self._work_order_lines():
            spring = line.get("spring")

            if spring and spring.get("door"):
                return spring["door"]

        # A KIT ORDER HAS NO SPRING TO READ. The dealer order writes the door
        # onto the kit line instead, and that was the only place this did not
        # look - so a kit ordered with a door specification printed a header
        # with no door on it.
        # THE FULLEST ANSWER, not the first one. Several lines on an order can
        # carry a note, and returning the first that yielded anything meant one
        # line with only a weight on it could win over the line that actually
        # describes the door.
        best = {}

        for text in order_lines.mapped("name"):
            facts = self._work_order_dealer_door(text or "")

            if len(facts) > len(best):
                best = facts

        return best

    # --- what is on the shelf -------------------------------------------------
    AVAILABILITY = {
        "assigned": "Ready",
        "partially_available": "Part only",
        "confirmed": "Not available",
        "waiting": "Waiting",
        "draft": "Draft",
        "done": "Done",
        "cancel": "Cancelled",
    }

    def _work_order_printed_at(self):
        """When this sheet was printed, in the reader's own timezone.

        A sheet lying on a bench is otherwise undateable, and an order that has
        changed since it was printed looks exactly like one that has not.
        """
        self.ensure_one()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())

        return stamp.strftime("%d %b %Y %H:%M")

    # --- gathering moves back into what was bought ----------------------------

    def _work_order_component_length(self, moves):
        """The cut length of a summarised group, e.g. "17.5 ft".

        A cable arrives as four moves - the reel and its sleeve, thimble and
        stop - and only one of them is a measurement. The fittings are counted
        in Units; the reel is consumed in feet, and that figure IS the cable
        length. So the length is the component measured in anything other than
        Units, rather than a part number this has to be told about.
        """
        inch = self.env["uom.uom"].with_context(active_test=False).search(
            [("name", "=", "in")], limit=1)

        for move in moves:
            name = (move.product_uom.name or "").strip().lower()

            if not name or name in ("units", "unit", "each", "pc", "pcs"):
                continue

            # IN INCHES, BECAUSE THAT IS WHAT THE REST OF THE SHEET IS IN.
            # Stock counts the reel in feet, and 17.5 ft is a stock figure; the
            # person cutting it works to 210", the same units as every track
            # length and every spring on the page.
            #
            # ASKED FOR, NOT CHECKED FOR. Odoo 19 took categories off uom.uom -
            # there is no category_id to compare any more - so whether a unit
            # is a length is decided by trying the conversion and believing the
            # answer. A unit that cannot reach inches keeps its own.
            if inch:
                try:
                    inches = move.product_uom._compute_quantity(
                        move.product_uom_qty, inch, round=False)
                except (UserError, ValueError):
                    inches = None

                if inches:
                    return self._work_order_inches(inches)

            return "%g %s" % (move.product_uom_qty, move.product_uom.name)

        return ""

    def _work_order_collapses(self, sale_line, moves):
        """Is this group one thing to summarise, or a set to list in full?

        A CABLE IS SUMMARISED AND A KIT IS NOT, and the difference is what the
        floor needs from each. A cable is a LENGTH CUT FROM STOCK: the reel,
        the sleeve, the thimble and the stop are how one cable is made, and
        listing them asks somebody to reassemble a bill of materials to learn
        that a customer bought one cable. A hardware kit is a set of whole
        parts, and every one of them has to be picked off a shelf - summarising
        it hides the work.

        So the test is the cut, not the explosion: a group is summarised when
        one of its components is measured in something other than Units, or
        when the thing bought is itself a cable. A kit's parts are all counted
        in whole units and its name is not a cable, so it is listed as picked.
        """
        if len(moves) < 2 or not sale_line:
            return False

        if self._work_order_component_length(moves):
            return True

        # The name is a second signal rather than the only one, so a cable
        # whose reel happens to be counted in Units still summarises.
        if self._work_order_kind(
                sale_line.product_id.display_name or "") == "cable":
            return True

        # AND A THIRD: what the group is MADE OF. The thing sold may be named
        # in a way this cannot read, while a reel, a sleeve and a thimble say
        # plainly what they are.
        #
        # EVERY part has to be a cable part, not merely one of them. A hardware
        # kit that happens to contain a cable is still a kit, and summarising
        # it would hide the rollers and hinges somebody has to pick.
        return all(
            self._work_order_kind(move.product_id.display_name or "") == "cable"
            for move in moves)

    def _work_order_groups(self):
        """The moves, gathered by the sale line they came from.

        ONE CART LINE IS ONE THING, however many moves it explodes into.
        Grouped by the sale line rather than by a list of part numbers, so a
        box of sleeves bought on its own is still a box of sleeves: it has a
        sale line of its own and nothing to group with.
        """
        self.ensure_one()
        groups = []
        index = {}

        for move in self.move_ids:
            key = move.sale_line_id.id if move.sale_line_id else ("move", move.id)
            position = index.get(key)

            if position is None:
                index[key] = len(groups)
                groups.append([move])
            else:
                groups[position].append(move)

        return groups

    def _work_order_lines(self):
        """Every product on this work order, in the order it appears.

        EVERY product, not only the ones this module understands. A sheet that
        silently drops the drum because it is neither a track nor a cable sends
        somebody to the shelf for half an order.
        """
        self.ensure_one()
        lines = []

        for group in self._work_order_groups():
            # A group that is not summarised is listed move by move, so a kit
            # shows every part that has to come off a shelf.
            if self._work_order_collapses(group[0].sale_line_id, group):
                lines.append(self._work_order_line(group, collapsed=True))
            else:
                lines.extend(self._work_order_line([m]) for m in group)

        return lines + self._work_order_unmoved_lines()

    def _work_order_unmoved_lines(self):
        """Ordered things that make no stock move, which still have to be made.

        A SHEET THAT LISTS ONLY MOVES IS NOT THE ORDER. A custom torsion spring
        assembly is made to order; if its product is a service, or anything
        else that moves no stock, Odoo puts no line on the transfer and the
        assembly was invisible here - no Springs page, no specification, and
        no door, because the door is written on that line.

        Somebody still has to wind it. So the order's own lines are read, and
        the ones that produced no move on this transfer are listed too.
        """
        self.ensure_one()
        order = self._work_order_sale_order()

        if not order:
            return []

        # Only on the first transfer of the order, so an order split across
        # several does not print these on every one of them.
        others = order.picking_ids.filtered(lambda p: p.id < self.id)

        if others:
            return []

        moved = order.order_line.browse()

        for picking in order.picking_ids:
            moved |= picking.move_ids.mapped("sale_line_id")

        # A move with no link still covers its line, matched by product, or the
        # same thing would print twice.
        for move in self.move_ids:
            moved |= self._work_order_order_line(move)

        lines = []

        for sale_line in order.order_line:
            if sale_line in moved or sale_line.display_type:
                continue

            if not sale_line.product_id or not sale_line.product_uom_qty:
                continue

            # ONLY WHAT CANNOT MOVE STOCK. A service never gets a move, so it
            # would otherwise never be seen. A GOOD that is simply not on this
            # transfer is a different matter - it is on another step, or not
            # delivered yet - and listing it here would put things on the sheet
            # that nobody is picking today.
            if sale_line.product_id.type != "service":
                continue

            # A SHIPPING LINE IS NOT SOMETHING TO MAKE. "Pickup - Medley
            # Warehouse" is a delivery method and a deposit is money; both are
            # service lines on the order and both turned up on the floor's
            # sheet under Hardware, marked "Made to order", which is exactly
            # what it reads like to somebody holding it.
            if "is_delivery" in sale_line._fields and sale_line.is_delivery:
                continue

            if "is_downpayment" in sale_line._fields and sale_line.is_downpayment:
                continue

            lines.append(self._work_order_sale_line(sale_line))

        return lines

    def _work_order_sale_line(self, sale_line):
        """One printed row for an ordered thing that moves no stock."""
        product = sale_line.product_id
        name = product.display_name or ""
        spring = self._work_order_spring_from_text(sale_line.name or "")
        kind = "spring" if spring else self._work_order_kind(name)
        category, source = self._work_order_category(product)

        return {
            "code": product.default_code or "",
            "name": product.name or name,
            # WHAT THIS ROW WAS MADE FROM. The printed sheet does not need
            # either, but the work stations do: a row has to be recognisable
            # as the same row when the same transfer is sorted again, or a
            # re-sort would double the queue and lose what a bench had
            # already ticked off.
            "product": product,
            "key": "sl%s" % sale_line.id,
            "quantity": sale_line.product_uom_qty,
            "uom": (sale_line.product_uom_id.name
                    if "product_uom_id" in sale_line._fields else "") or "",
            "kind": kind,
            "length": self._work_order_length(name),
            "spring": spring,
            # It is not on a shelf and never will be, so saying "Not available"
            # would send somebody looking for it.
            "availability": "Made to order",
            "short": False,
            "parts": 1,
            "category": category,
            "category_source": source,
            "page": self._work_order_page(kind, category),
        }

    def _work_order_line(self, moves, collapsed=False):
        """One printed row: one move, or a summarised group of them."""
        move = moves[0]
        sale_line = move.sale_line_id

        # What the CUSTOMER bought, when several moves are one purchase.
        product = sale_line.product_id if collapsed else move.product_id
        name = product.display_name or ""
        spring = self._work_order_spring(move)
        length = self._work_order_length(name)

        if collapsed:
            length = self._work_order_component_length(moves) or length

        kind = "spring" if spring else self._work_order_kind(name)

        # A SUMMARISED GROUP TAKES ITS KIND FROM WHAT IT IS MADE OF. The thing
        # sold may be named in a way this cannot read, while its components -
        # a GAC reel, an oval sleeve, a thimble - say plainly what it is.
        if not kind and len(moves) > 1:
            for part in moves:
                found = self._work_order_kind(part.product_id.display_name or "")

                if found:
                    kind = found
                    break

        category, source = self._work_order_category(product)
        states = [m.state for m in moves]
        short = [st for st in states
                 if st in ("confirmed", "waiting", "partially_available")]
        state = short[0] if short else states[0]

        return {
            "code": product.default_code or "",
            "name": product.name or name,
            "product": product,
            # A collapsed group is one purchase and keys on the line it came
            # from; a single move keys on itself, which is the only identity a
            # move with no order line behind it has.
            "key": ("sl%s" % sale_line.id if collapsed and sale_line
                    else "mv%s" % move.id),
            "quantity": (sale_line.product_uom_qty if collapsed
                         else move.product_uom_qty),
            "uom": ((sale_line.product_uom_id.name
                     if collapsed and "product_uom_id" in sale_line._fields
                     else move.product_uom.name) or ""),
            "kind": kind,
            "length": length,
            "spring": spring,
            "availability": self.AVAILABILITY.get(state, state or ""),
            "short": bool(short),
            "parts": len(moves),
            "category": category,
            "category_source": source,
            "page": self._work_order_page(kind, category),
        }

    # --- which page a line belongs on -----------------------------------------

    def _work_order_category(self, product):
        """The category to file this product under, and where it came from.

        THE SHOP CATEGORISES IN THE ECOMMERCE TREE, not the accounting one.
        Drums, Tracks, Shafts, Hinges, Rollers, EBF, Motors, Springs, Misc.,
        Hardware Kits, Nuts & Bolts - all of it lives in public_categ_ids,
        which is what Website > eCommerce > Categories edits. categ_id, the
        field reached for first, is untouched and empty, which is why every
        line came back uncategorised while eleven categories were plainly on
        screen.

        categ_id is still read, second, for a product filed there and not in
        the shop tree - and because a database without website_sale has no
        other category to offer.

        A product can sit in several eCommerce categories. The first by the
        owner's own ordering wins, because a line printed on two pages is a
        part picked twice.
        """
        if "public_categ_ids" in product._fields and product.public_categ_ids:
            ordered = product.public_categ_ids.sorted(
                lambda c: (c.sequence, c.name or "", c.id))

            return ordered[0], "public"

        if product.categ_id:
            return product.categ_id, "internal"

        return self.env["product.category"].browse(), ""

    # FOUR PAGES, AND NO MORE. The shop asked for Tracks, Springs, Cables and
    # Hardware, and for everything else - Drums, Hinges, Rollers, Shafts, EBF,
    # Motors, Nuts & Bolts, Misc. - to be swept into Hardware. The eCommerce
    # tree stays as it is for the website; this is how the FLOOR wants the work
    # divided, and the two are allowed to differ.
    #
    # Cables has no eCommerce category at all - it is a page that exists only
    # on this sheet - so it is decided by what the product is rather than by
    # where it is filed.
    PAGES = ("Tracks", "Springs", "Cables", "Hardware")
    PAGE_BY_CATEGORY = {
        "tracks": "Tracks",
        "springs": "Springs",
        "cables": "Cables",
    }
    PAGE_BY_KIND = {
        "spring": "Springs",
        "cable": "Cables",
        "track": "Tracks",
    }

    def _work_order_page(self, kind, category):
        """Which of the four pages this line prints on.

        The category decides it when the shop has filed the product under one
        of the three the floor keeps. Otherwise what the product IS decides -
        which is the only thing that can place a cable, because there is no
        Cables category to file one under. Anything left is Hardware, which is
        the point of Hardware: it is the box, not a leftover.
        """
        # A CABLE IS A CABLE WHEREVER IT IS FILED. The shop keeps its lift
        # cables under the Tracks category, so reading the category first put
        # them on the tracks page - and Cables is a page that exists only on
        # this sheet, with no category of its own to be filed under. What the
        # product IS decides this one, and nothing else can.
        if kind == "cable":
            return "Cables"

        name = (category.name or "").strip().lower() if category else ""
        page = self.PAGE_BY_CATEGORY.get(name)

        if page:
            return page

        return self.PAGE_BY_KIND.get(kind, "Hardware")

    def _work_order_sections(self):
        """The lines gathered onto the four pages the floor works from.

        Always in the same order, and a page with nothing on it is left out -
        an order of tracks alone is one page, not four with three empty.
        """
        self.ensure_one()
        groups = {}

        for line in self._work_order_lines():
            groups.setdefault(line["page"], []).append(line)

        return [{
            "title": page,
            "parent": "",
            "uncategorised": False,
            "lines": groups[page],
        } for page in self.PAGES if groups.get(page)]

    # --- sorting the work onto the benches ------------------------------------
    #
    # THE SAME RULE THAT SORTS THE PRINTED SHEET, deliberately and without a
    # second copy of it. _work_order_page already decides whether a line is a
    # track, a spring or a cable - by what the product IS first and where the
    # shop filed it second - and every one of those decisions is tested. A
    # station is simply that page with a tablet in front of it, so the sort
    # reads the sheet's own lines and files them by page name.
    #
    # Hardware is not a station: those parts come off a shelf against the
    # transfer, which is what the transfer is for.

    def _work_station_door_label(self, door):
        """The door, on one line, for the bench that is building for it."""
        door = door or {}
        size = " x ".join(filter(None, [door.get("width"), door.get("height")]))

        return " | ".join(filter(None, [
            size,
            door.get("weight"),
            ('%s hi-lift' % door["hilift"]) if door.get("hilift") else "",
        ]))

    def _work_station_detail(self, line):
        """The specification a bench has to work to, as plain text.

        ONLY THE SPRINGS HAVE ONE. A track and a cable are a length, and the
        length has a column of its own; an assembly is a cut list, and that is
        what this is.
        """
        spring = line.get("spring")

        if not spring:
            return ""

        facts = dict(spring.get("parameters") or [])
        rows = []
        head = []

        if facts.get("Assembly"):
            head.append(facts["Assembly"])

        if facts.get("Springs"):
            count = facts["Springs"]
            head.append("%s spring%s" % (count, "" if count == "1" else "s"))

        if head:
            rows.append(", ".join(head))

        for item in spring.get("springs") or []:
            rows.append('%s: %s wire, %s ID, %s long' % (
                item.get("role") or "Spring", item.get("wire") or "?",
                item.get("inside_diameter") or "?", item.get("length") or "?"))

        if facts.get("Cycle target"):
            rows.append("%s cycles" % facts["Cycle target"])

        return "\n".join(rows)

    # WHAT DISPATCH HAS NO WORK TO DO ON.
    #
    # Perforated angles, shafts and trims are supplied as they come, so they
    # arrive at dispatch already complete and there is nothing for anybody to
    # tick off - which is also why they cannot be put back: there is no work to
    # undo. The owner's rule, 2026-10-13.
    #
    # A FLAG ANGLE IS NOT A PERFORATED ANGLE, and that is the one mistake this
    # must not make. Flag angles are real work on a prepared track - the
    # calculator adds one per track - so "angle" on its own would have quietly
    # marked them complete and sent somebody a door with no flag angle fitted.
    # The word perforated is required, in either order, and nothing matches on
    # "angle" alone.
    #
    # ONLY AT DISPATCH. These are properties of a part that is gathered, not of
    # one that is made: if a product named for a shaft ever sorts to a making
    # bench, that bench is doing something to it and still says when it is
    # done.
    AUTO_DONE = (
        ("perforated angle", re.compile(
            r"\bperf(?:orated)?\w*\b.*\bangles?\b"
            r"|\bangles?\b.*\bperf(?:orated)?\w*\b", re.I)),
        ("shaft", re.compile(r"\bshafts?\b", re.I)),
        ("trim", re.compile(r"\btrims?\b", re.I)),
    )

    def _work_station_auto_done(self, name):
        """The kind of thing this is, when it needs no work, or ""."""
        for kind, pattern in self.AUTO_DONE:
            if pattern.search(name or ""):
                return kind

        return ""

    # WHICH BENCH EACH PAGE FEEDS. Three of them are the same word twice;
    # Hardware feeds Dispatch, because a hinge is not made, it is gathered and
    # sent. The page is what a part IS and the station is who handles it, which
    # is why this is a mapping and not a lowercase().
    PAGE_TO_STATION = {
        "springs": "springs",
        "tracks": "tracks",
        "cables": "cables",
        "hardware": DISPATCH,
    }

    def _work_station_values(self):
        """[(station code, values)] for everything on this transfer to do."""
        self.ensure_one()
        door = self._work_station_door_label(self._work_order_door())
        order = self._work_order_sale_order()
        wanted = []
        sequence = 10

        for line in self._work_order_lines():
            code = self.PAGE_TO_STATION.get((line.get("page") or "").lower())

            if not code:
                continue

            product = line.get("product")
            # Named by what was BOUGHT, which is the name the floor reads and
            # the one the sheet prints.
            auto = (self._work_station_auto_done(line.get("name") or "")
                    if code == DISPATCH else "")
            wanted.append((code, {
                "auto_done": bool(auto),
                "auto_done_kind": auto,
                "picking_id": self.id,
                "order_name": order.name if order else (self.origin or self.name),
                "sequence": sequence,
                "product_id": product.id if product else False,
                "name": line.get("name") or "",
                "code": line.get("code") or "",
                "quantity": line.get("quantity") or 0.0,
                "uom_name": line.get("uom") or "",
                "length": line.get("length") or "",
                "door": door,
                "detail": self._work_station_detail(line),
                "line_key": line.get("key") or "",
            }))
            sequence += 10

        return wanted

    def _work_station_sync(self):
        """Put this transfer's work on the benches that do it.

        IDEMPOTENT, because it runs again every time the transfer is
        confirmed. A row already on a station is updated in place, so a bench
        that has ticked something off does not see it come back; a row that is
        no longer on the transfer is removed unless it is already done, since
        deleting finished work would lose the only record that it happened.
        """
        Item = self.env["work.station.item"].sudo()
        Station = self.env["work.station"].sudo()

        for picking in self:
            if picking.state in ("draft", "cancel"):
                continue

            existing = Item.search([("picking_id", "=", picking.id)])
            by_key = {item.line_key: item for item in existing}
            seen = set()
            created = Item.browse()

            for code, values in picking._work_station_values():
                station = Station._station_for_code(code)

                if not station:
                    continue

                values["station_id"] = station.id
                seen.add(values["line_key"])
                item = by_key.get(values["line_key"])

                if item:
                    # NEVER THE STATE. A re-sort describes the work again; it
                    # does not un-finish it.
                    item.write(values)
                else:
                    if values.get("auto_done"):
                        # Complete the moment it is sorted: there is nothing
                        # for a bench to do to it.
                        values = dict(values, state="done",
                                      done_at=fields.Datetime.now())

                    created |= Item.create(values)

            # LOGGED ONCE, WHEN THEY ARRIVE. Otherwise the order's log would
            # show a dispatch that finished work nobody remembers doing, and a
            # re-sort would say it again - only newly created rows are listed,
            # and an existing row is updated rather than made.
            created.filtered("auto_done")._work_station_log_auto_done()

            stale = existing.filtered(
                lambda i: i.line_key not in seen and i.state == "todo")
            stale.unlink()

        return True

    def action_confirm(self):
        """Confirming a transfer is what puts its work on the benches."""
        result = super().action_confirm()
        self._work_station_sync()

        return result

    def action_work_station_sync(self):
        """The Actions menu entry, for a transfer confirmed before this
        existed - or one whose products were corrected afterwards."""
        self._work_station_sync()

        return True

    # --- what the benches have finished, on the order itself -------------------
    #
    # THE OFFICE ASKS THIS ALL DAY. "Are the springs done?" was answerable only
    # by opening the station queues or walking to the bench, so the work order
    # itself now carries one line per station: Done, In progress, To do, or
    # nothing at all when that bench has no part in this order.
    #
    # IN PROGRESS IS WORTH ITS OWN WORD. Two of three tracks cut is neither
    # done nor untouched, and an order that reads "To do" when a bench is half
    # way through it sends somebody to ask the question this is meant to
    # answer.
    WORK_STATION_STATES = [
        ("none", "Not needed"),
        ("todo", "To do"),
        ("partial", "In progress"),
        ("done", "Done"),
    ]

    work_station_item_ids = fields.One2many(
        "work.station.item", "picking_id", string="Station work")

    # PUT ON THE BENCHES BY HAND, NOT BY CONFIRMING AN ORDER.
    #
    # The work is sorted as soon as a transfer is confirmed - that part has not
    # changed - but a bench screen showing every confirmed order is a bench
    # screen showing work the office has not finished thinking about: an order
    # still being edited, one waiting on a part, one that is not this week's.
    # So the sorting and the SHOWING are now two different things, and the
    # second one is a decision somebody makes in the Work Orders list.
    #
    # A FLAG RATHER THAN DELETING THE ROWS. Taking an order back off the
    # benches has to be as safe as putting it there - it hides the work and
    # keeps every tick already made, so an order put back a day later does not
    # ask anybody to do the same job twice.
    work_station_released = fields.Boolean(
        string="On the work stations", copy=False, index=True)
    work_station_springs = fields.Selection(
        WORK_STATION_STATES, string="Springs", default="none",
        compute="_compute_work_station_states", store=True)
    work_station_tracks = fields.Selection(
        WORK_STATION_STATES, string="Tracks", default="none",
        compute="_compute_work_station_states", store=True)
    work_station_cables = fields.Selection(
        WORK_STATION_STATES, string="Cables", default="none",
        compute="_compute_work_station_states", store=True)
    work_station_dispatch = fields.Selection(
        WORK_STATION_STATES, string="Hardware", default="none",
        compute="_compute_work_station_states", store=True)
    work_station_todo_count = fields.Integer(
        string="Still to make", compute="_compute_work_station_states",
        store=True)

    # The code each field holds, so the compute and the form stay in step.
    WORK_STATION_FIELDS = (
        ("springs", "work_station_springs"),
        ("tracks", "work_station_tracks"),
        ("cables", "work_station_cables"),
        (DISPATCH, "work_station_dispatch"),
    )

    @api.depends("work_station_item_ids.state",
                 "work_station_item_ids.station_id")
    def _compute_work_station_states(self):
        """STORED, so the office can filter a list by it rather than open
        every order to find the one the floor is waiting on."""
        for picking in self:
            states = {}

            for item in picking.work_station_item_ids:
                states.setdefault(item.station_id.code, []).append(item.state)

            for code, field in self.WORK_STATION_FIELDS:
                here = states.get(code) or []

                if not here:
                    value = "none"
                elif all(state == "done" for state in here):
                    value = "done"
                elif any(state == "done" for state in here):
                    value = "partial"
                else:
                    value = "todo"

                picking[field] = value

            picking.work_station_todo_count = sum(
                1 for state in sum(states.values(), []) if state != "done")

    def action_work_station_release(self):
        """Show these orders on the benches that do their work.

        RE-SORTED AS IT GOES, because an order confirmed last week and edited
        since must reach the bench as it is now, not as it was when it was
        confirmed.
        """
        self._work_station_sync()

        for picking in self:
            if picking.work_station_released:
                continue

            picking.work_station_released = True
            picking.message_post(
                body=self.env._("Sent to the work stations."),
                subtype_xmlid="mail.mt_note")

        return True

    def action_work_station_withdraw(self):
        """Take them off the benches again, keeping every tick already made."""
        for picking in self:
            if not picking.work_station_released:
                continue

            picking.work_station_released = False
            picking.message_post(
                body=self.env._("Taken off the work stations."),
                subtype_xmlid="mail.mt_note")

        return True

    def action_open_work_station_items(self):
        """The station rows behind those three words."""
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Station work",
            "res_model": "work.station.item",
            "view_mode": "list",
            "domain": [("picking_id", "=", self.id)],
            "context": {"search_default_by_station": 1},
        }

    # --- dispatch goes last, and finishes the job -----------------------------

    @api.depends("work_station_springs", "work_station_tracks",
                 "work_station_cables")
    def _compute_work_station_ready_to_dispatch(self):
        """Have the three making benches finished with this order?

        A BENCH WITH NOTHING TO MAKE IS NOT IN THE WAY. An order of hardware
        alone has no springs, tracks or cables on it, so it is ready to go out
        the moment it is picked - waiting for three benches that were never
        given anything would be a transfer that could never leave.
        """
        for picking in self:
            waiting = [
                self.env["work.station"]._station_label(code)
                for code, field in self.WORK_STATION_FIELDS
                if code in MAKERS and picking[field] not in ("none", "done")
            ]
            picking.work_station_waiting_for = ", ".join(waiting)
            picking.work_station_ready_to_dispatch = not waiting

    work_station_ready_to_dispatch = fields.Boolean(
        string="Ready to dispatch",
        compute="_compute_work_station_ready_to_dispatch")
    work_station_waiting_for = fields.Char(
        string="Waiting for", compute="_compute_work_station_ready_to_dispatch")

    def _work_station_complete(self):
        """Dispatch's final confirmation: this order is finished, send it.

        THE BUTTON IS THE CONFIRMATION, not the last tick. Every station being
        done means the work is made; it does not mean the order has left. One
        deliberate press says that, which is why validating the transfer hangs
        off this and not off the last box being ticked.

        Returns "" when the order closed, or the reason it could not - which
        the bench is shown rather than left to guess at.
        """
        self.ensure_one()

        if self.state in ("done", "cancel"):
            return ""

        if self.work_station_todo_count:
            raise UserError(self.env._(
                "This order is not finished yet: %(count)s things on it are "
                "still to do.",
                count=self.work_station_todo_count,
            ))

        refused = self._work_station_finish()
        reason = refused.get(self.id, "")

        if not reason:
            # NAMED FROM THE RECORD, not written out here: the owner renamed
            # this bench once and may again, and a log that still says
            # Dispatch when the screen says Hardware is a log somebody has to
            # translate in their head.
            self.sudo().message_post(
                body=self.env._(
                    "%(station)s confirmed this order as complete, and the "
                    "transfer was validated.",
                    station=self.env["work.station"]._station_label(DISPATCH)),
                subtype_xmlid="mail.mt_note")

        return reason

    def _work_station_finish(self):
        """Validate the transfers whose work is all done.

        Returns {picking id: reason} for any that could not be closed.

        BUT IT IS ATTEMPTED, NOT ASSUMED. Validating a transfer moves stock,
        and Odoo quite rightly refuses some of them unattended - nothing
        reserved, a lot or serial number still to give, a backorder to decide
        about. A refusal must not lose the fact that the work was done or leave
        an error on a screen bolted to a bench, so the work stays ticked off,
        the reason is written in the transfer's own chatter for the office to
        pick up, and the floor is told in one line. Everything the bench did is
        recorded either way.
        """
        refused = {}

        for picking in self:
            if picking.state in ("done", "cancel"):
                continue

            # Every bench, dispatch included. A transfer is not finished while
            # anything on it is still to make.
            if picking.work_station_todo_count:
                continue

            try:
                # WHAT DISPATCH TICKING OFF MEANS: the goods have left the
                # building. So a move with no quantity on it is filled from
                # what was ordered and marked picked, because the alternative
                # is a transfer that can never close - Odoo refuses to validate
                # one with nothing on it, and an order sitting at Confirmed
                # forever is exactly what the owner asked to be rid of.
                #
                # THIS CAN DRIVE STOCK NEGATIVE, and that is the honest
                # outcome: if the hardware went out and the system thought
                # there was none, the count was already wrong and now says so.
                # It is not this code's place to hide that by refusing to
                # record the dispatch.
                moves = picking.sudo().move_ids.filtered(
                    lambda move: move.state not in ("done", "cancel"))

                for move in moves:
                    if not move.quantity:
                        move.quantity = move.product_uom_qty

                moves.picked = True

                # skip_backorder, because a wizard asking what to do about the
                # rest of the order is a question for the office, not for a
                # tablet. Anything left undelivered stays on the transfer.
                result = picking.sudo().with_context(
                    skip_backorder=True, skip_sms=True,
                ).button_validate()
            except (UserError, ValidationError) as error:
                refused[picking.id] = str(error)
                continue

            picking.invalidate_recordset(["state"])

            if picking.state != "done":
                # button_validate answered with a wizard or a report instead of
                # finishing. Nothing is broken; it simply needs a person.
                refused[picking.id] = self._work_station_office_message(result)

        for picking in self:
            reason = refused.get(picking.id)

            if reason:
                picking.sudo().message_post(
                    body=self.env._(
                        "%(station)s confirmed this order as finished, but "
                        "the transfer could not be validated automatically: "
                        "%(reason)s",
                        station=self.env["work.station"]._station_label(
                            DISPATCH),
                        reason=reason,
                    ),
                    subtype_xmlid="mail.mt_note")

        return refused

    def _work_station_office_message(self, result):
        """Why a validation that raised nothing still did not finish."""
        if isinstance(result, dict):
            return self.env._("it needs to be confirmed in the back office")

        return self.env._("it is not in a state that can be validated")
