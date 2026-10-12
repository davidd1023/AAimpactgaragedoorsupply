import re

from odoo import fields, models
from odoo.exceptions import UserError

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

KINDS = (
    ("track", re.compile(r"\btrack\b", re.I)),
    ("cable", re.compile(r"\bcable\b", re.I)),
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

    def _work_order_spring(self, move):
        """The assembly behind this line, read off its description, or None.

        GUARDED RATHER THAN DEPENDED ON. This module prints transfers and knows
        nothing about torsion springs; it recognises the description the spring
        calculator writes and prints what it finds, so it works on a database
        without the calculator and needs no bridge module.
        """
        line = move.sale_line_id if "sale_line_id" in move._fields else False
        text = (line.name or "") if line else ""
        rows = [r for r in text.splitlines() if r.strip()]

        if not rows or self.SPRING_MARKER not in rows[0].strip().lower():
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
    DEALER_DIMS = re.compile(r"\bW\s*([^|x]+?)\s*x\s*H\s*([^|]+?)\s*(?:\||$)", re.I)
    # The trailing inch mark is appended, as above: a raw literal cannot end
    # in a quote.
    DEALER_HILIFT = re.compile(
        r"(?:high\s*lift|hi-?lift)\s*([\d.]+)\s*" + '"', re.I)

    def _work_order_dealer_door(self, text):
        """The door facts a dealer kit order carries, or {}."""
        facts = {}
        dims = self.DEALER_DIMS.search(text or "")

        if dims:
            facts["width"] = dims.group(1).strip()
            facts["height"] = dims.group(2).strip()

        weight = self.DOOR_WEIGHT.search(text or "")

        if weight:
            facts["weight"] = "%s lb" % weight.group(1)

        hilift = self.DEALER_HILIFT.search(text or "")

        if hilift:
            facts["hilift"] = '%s"' % hilift.group(1)

        return facts

    def _work_order_door(self):
        """The door this whole order is for, if anything on it says.

        Taken from the spring assembly, which is the only thing a website order
        carries that describes a door. Printed on EVERY page, because a track
        cutter holding the tracks page is cutting for that same door.
        """
        self.ensure_one()

        for line in self._work_order_lines():
            spring = line.get("spring")

            if spring and spring.get("door"):
                return spring["door"]

        # A KIT ORDER HAS NO SPRING TO READ. The dealer order writes the door
        # onto the kit line instead, and that was the only place this did not
        # look - so a kit ordered with a door specification printed a header
        # with no door on it.
        for move in self.move_ids:
            sale_line = move.sale_line_id

            if not sale_line:
                continue

            facts = self._work_order_dealer_door(sale_line.name or "")

            if facts:
                return facts

        return {}

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
        return self._work_order_kind(
            sale_line.product_id.display_name or "") == "cable"

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

        return lines

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

        category, source = self._work_order_category(product)
        states = [m.state for m in moves]
        short = [st for st in states
                 if st in ("confirmed", "waiting", "partially_available")]
        state = short[0] if short else states[0]

        return {
            "code": product.default_code or "",
            "name": product.name or name,
            "quantity": (sale_line.product_uom_qty if collapsed
                         else move.product_uom_qty),
            "uom": ((sale_line.product_uom_id.name
                     if collapsed and "product_uom_id" in sale_line._fields
                     else move.product_uom.name) or ""),
            "kind": "spring" if spring else self._work_order_kind(name),
            "length": length,
            "spring": spring,
            "availability": self.AVAILABILITY.get(state, state or ""),
            "short": bool(short),
            "parts": len(moves),
            "category": category,
            "category_source": source,
            "page": self._work_order_page(
                "spring" if spring else self._work_order_kind(name), category),
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
