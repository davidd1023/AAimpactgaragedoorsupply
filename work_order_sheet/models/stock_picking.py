import re

from odoo import fields, models

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

        return self._work_order_inches(hit.group(1).strip().replace(" ", ""))

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

    # --- 2. what the picker needs to know before walking to the shelf -------
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
                    "wire": self._work_order_inches(hit.group(2), fraction=False),
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

    def _work_order_component_length(self, moves):
        """The cut length of a collapsed group, e.g. "17.5 ft".

        A cable arrives as four moves - the reel and its sleeve, thimble and
        stop - and only one of them is a measurement. The fittings are counted
        in Units; the reel is consumed in feet, and that figure IS the cable
        length. So the length is the component measured in anything other than
        Units, rather than a part number this has to be told about.
        """
        for move in moves:
            name = (move.product_uom.name or "").strip().lower()

            if name and name not in ("units", "unit", "each", "pc", "pcs"):
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

        So the test is the cut, not the explosion. A group is summarised when
        one of its components is measured in something other than Units - feet
        of cable off a reel - or when the thing bought is itself a cable. A
        kit's components are all counted in whole units and its name is not a
        cable, so it is listed exactly as it is picked.
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
        """The moves, gathered back into the things a customer bought.

        ONE CART LINE IS ONE THING, however many moves it explodes into. A
        cable is sold as a cable and picked as four moves - reel, sleeve,
        thimble, stop - and a sheet listing all four asks the floor to read a
        bill of materials to find out that somebody bought one cable.

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
            collapses = self._work_order_collapses(group[0].sale_line_id, group)

            if collapses:
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
            "category": product.categ_id,
        }

    # What to call a page when the products on it have no category. These are
    # read off the product name by _work_order_kind, which is the only thing
    # this module can know without the catalogue telling it.
    KIND_TITLES = {
        "spring": "Springs",
        "track": "Tracks",
        "cable": "Cables",
        "": "Other",
    }

    def _work_order_sections(self):
        """The lines grouped by the category each product is filed under.

        THE CATALOGUE ALREADY KNOWS THIS. The first version sorted into four
        buckets named in this file - springs, tracks, cables, everything else -
        which meant a shop with Brackets, Hinges, Struts, Rollers and Drums &
        Shaft Parts saw them all land in "Hardware and Other", and adding a
        category meant editing code. Odoo has a category on every product and
        a tree the owner maintains, so that is what decides the pages.

        Ordered by the category's full path, so children sit under their
        parent and the same order comes out every time. Only categories with
        something in them get a page.
        """
        self.ensure_one()
        lines = self._work_order_lines()
        groups = {}

        for line in lines:
            category = line["category"]
            # A PRODUCT WITH NO CATEGORY IS NORMAL, not a mistake to print.
            # categ_id is not required in Odoo 19 and has no default, so a
            # product created without one simply has none - and a sheet that
            # answers that with a single "Uncategorised" page is true and
            # useless. What this module can still tell from the name is used
            # instead, and the page says the category is missing so the
            # catalogue gets fixed rather than the sheet being worked around.
            key = category.id if category else ("kind", line["kind"])
            groups.setdefault(key, (category, line["kind"], []))[2].append(line)

        sections = []

        for category, kind, rows in groups.values():
            if category:
                sections.append({
                    "title": category.name,
                    # The path disambiguates two leaves that share a name - a
                    # Tracks under Hardware and a Tracks somewhere else are two
                    # pages, and the heading alone would not say which.
                    "path": category.complete_name or category.name,
                    "parent": (category.parent_id.complete_name or ""
                               if category.parent_id else ""),
                    "uncategorised": False,
                    "lines": rows,
                })
                continue

            sections.append({
                "title": self.KIND_TITLES.get(kind, "Other"),
                # Sorted after every real category, so a catalogue that is
                # fully filed in reads top to bottom and a half-filed one puts
                # its loose ends at the back rather than in the middle.
                "path": "zzz %s" % self.KIND_TITLES.get(kind, "Other"),
                "parent": "",
                "uncategorised": True,
                "lines": rows,
            })

        return sorted(sections, key=lambda s: (s["path"], s["title"]))

    def _work_order_printed_at(self):
        """When this sheet was printed, in the reader's own timezone.

        A sheet lying on a bench is otherwise undateable, and an order that has
        changed since it was printed looks exactly like one that has not.
        """
        self.ensure_one()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())

        return stamp.strftime("%d %b %Y %H:%M")

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
                    "wire": self._work_order_inches(hit.group(2), fraction=False),
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

    def _work_order_component_length(self, moves):
        """The cut length of a collapsed group, e.g. "17.5 ft".

        A cable arrives as four moves - the reel and its sleeve, thimble and
        stop - and only one of them is a measurement. The fittings are counted
        in Units; the reel is consumed in feet, and that figure IS the cable
        length. So the length is the component measured in anything other than
        Units, rather than a part number this has to be told about.
        """
        for move in moves:
            name = (move.product_uom.name or "").strip().lower()

            if name and name not in ("units", "unit", "each", "pc", "pcs"):
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

        So the test is the cut, not the explosion. A group is summarised when
        one of its components is measured in something other than Units - feet
        of cable off a reel - or when the thing bought is itself a cable. A
        kit's components are all counted in whole units and its name is not a
        cable, so it is listed exactly as it is picked.
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
        """The moves, gathered back into the things a customer bought.

        ONE CART LINE IS ONE THING, however many moves it explodes into. A
        cable is sold as a cable and picked as four moves - reel, sleeve,
        thimble, stop - and a sheet listing all four asks the floor to read a
        bill of materials to find out that somebody bought one cable.

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
            collapses = self._work_order_collapses(group[0].sale_line_id, group)

            if collapses:
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
            "category": product.categ_id,
        }

