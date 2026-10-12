import json
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# The four track types the calculator offers, and the nominal size of each.
# The size decides which stock length a track is cut from.
TRACK_TYPES = {
    "3-15R": ('3"', '3" 15R'),
    "2-12R": ('2"', '2" 12R'),
    "3-LHR": ('3"', '3" LHR'),
    "2-LHR": ('2"', '2" LHR'),
}

LIFT_TYPES = {
    "standard": "Standard Lift",
    "highlift": "High Lift",
    "lhr": "Low Headroom",
}

# The cable the calculator calls for, and the setting that says which reel it
# comes off. The calculator derives this from the drum - CTYPE in its source -
# so these three are the whole set.
CABLE_SIZES = {
    '1/8"': "door_work_order.cable_18_product_id",
    '5/32"': "door_work_order.cable_532_product_id",
    '3/16"': "door_work_order.cable_316_product_id",
}

# Name fragments to fall back on when a cable reel has not been configured.
# The live catalogue holds "1/8\" 7x19 Cable 500ft Reel" and its two siblings,
# which is unambiguous enough to guess from - once, as a default.
CABLE_FALLBACK_NAME = {
    '1/8"': '1/8" 7x19 Cable',
    '5/32"': '5/32" 7x19 Cable',
    '3/16"': '3/16" 7x19 Cable',
}

# The calculator's own input limits, repeated here because a limit enforced
# only in the browser is not enforced at all - this endpoint is reachable with
# any URL a logged-in user cares to type.
BOUNDS = {
    "width": (84.0, 216.0),
    "height": (84.0, 144.0),
    "vertical": (1.0, 400.0),
    "horizontal": (1.0, 400.0),
    "cable": (1.0, 600.0),
    "weight": (1.0, 5000.0),
    "hilift": (0.0, 240.0),
    "projection": (0.0, 60.0),
    "ftsc": (0.0, 600.0),
    "capacity": (0.0, 10000.0),
    "door_qty": (1.0, 999.0),
}


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    door_wo_reference = fields.Char(
        string="Door W/O",
        index=True,
        copy=False,
        help="The work order number from the door calculator.",
    )
    door_wo_mark = fields.Char(string="Mark", copy=False)
    door_wo_summary = fields.Text(
        string="Door Specification",
        copy=False,
        help="The door this cut list came from, as the calculator described it.",
    )
    door_wo_item_ids = fields.One2many(
        "door.work.order.item",
        "production_id",
        string="Cut List",
        copy=False,
    )
    door_wo_mark_ids = fields.One2many(
        "door.work.order.mark", "production_id", string="Marks", copy=False)
    door_wo_item_count = fields.Integer(compute="_compute_door_wo_item_count")

    # WHAT THE TWO INFO PAPERS PRINT. These are carried from the calculator
    # rather than recomputed here, and that is deliberate. The calculator lets
    # the shop OVERRIDE the jamb bracket quantities in its own settings, so a
    # figure recomputed in Odoo would quietly contradict the one the person
    # read off the screen. The drum, EBF and capacity tables would likewise
    # become a second copy free to drift from the first. The papers are meant
    # to reproduce what the calculator showed, so they carry what it showed.
    door_wo_width = fields.Float(string="Door Width (in)", copy=False)
    door_wo_height = fields.Float(string="Door Height (in)", copy=False)
    door_wo_weight = fields.Float(string="Door Weight (lb)", copy=False)
    door_wo_track_label = fields.Char(string="Track", copy=False)
    door_wo_config = fields.Char(string="Configuration", copy=False)
    door_wo_projection = fields.Float(string="2x2 Projection (in)", copy=False)
    door_wo_sections = fields.Integer(string="Sections", copy=False)
    door_wo_drum = fields.Char(string="Drum", copy=False)
    door_wo_ebf = fields.Char(string="EBF", copy=False)
    door_wo_capacity = fields.Float(string="Capacity Per Drum (lb)", copy=False)
    door_wo_ftsc = fields.Float(string="FTSC (in)", copy=False)
    door_wo_cable_type = fields.Char(string="Cable Type", copy=False)
    # ZERO MEANS "NOT APPLICABLE", which is what the calculator prints as "--".
    # The #16 bracket does not appear at all below a 97" vertical track, and no
    # band of the table ever calls for zero of a size it does list, so zero is
    # free to carry the absence.
    door_wo_jb_10 = fields.Integer(string="J-10", copy=False)
    door_wo_jb_12 = fields.Integer(string="J-12", copy=False)
    door_wo_jb_14 = fields.Integer(string="J-14", copy=False)
    door_wo_jb_16 = fields.Integer(string="J-16", copy=False)

    door_wo_has_papers = fields.Boolean(compute="_compute_door_wo_has_papers")

    @api.depends("door_wo_item_ids", "door_wo_width")
    def _compute_door_wo_has_papers(self):
        for production in self:
            production.door_wo_has_papers = bool(production.door_wo_item_ids)

    def _door_wo_item_length(self, role):
        """The cut length for one role, or 0 - for the papers to print."""
        self.ensure_one()
        item = self.door_wo_item_ids.filtered(lambda i: i.role == role)[:1]

        return item.length_label or ""

    @api.depends("door_wo_item_ids")
    def _compute_door_wo_item_count(self):
        for production in self:
            production.door_wo_item_count = len(production.door_wo_item_ids)

    # --- reading the calculator's numbers ------------------------------------

    @api.model
    def _door_wo_inches_label(self, value):
        """76.25 -> '76 1/4"', the way the calculator prints it.

        It snaps to the nearest eighth, as the calculator's own frac() does, so
        the order reads in the units the shop floor measures in rather than in
        decimals nobody has a tape for.
        """
        whole = int(math.floor(value))
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

    @api.model
    def _door_wo_number(self, raw, key, required=True):
        """A number from the spec, inside its bounds, or a clear refusal."""
        if raw in (None, "", False):
            if required:
                raise UserError(_("The door calculator sent no %s.", key))

            return 0.0

        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise UserError(
                _("The %(key)s the calculator sent is not a number: %(value)r",
                  key=key, value=raw)
            )

        if not (value == value) or value in (float("inf"), float("-inf")):
            raise UserError(_("The %s the calculator sent is not a number.", key))

        low, high = BOUNDS[key]

        if not low <= value <= high:
            raise UserError(
                _("A %(key)s of %(value)s is outside what this makes orders for"
                  " (%(low)s to %(high)s). Nothing was created.",
                  key=key, value=("%g" % value), low=("%g" % low),
                  high=("%g" % high))
            )

        return value

    @api.model
    def _door_wo_parse(self, spec):
        """Validate what the calculator sent and return it as plain values.

        NOTHING THE SENDER SAYS ABOUT PRODUCTS IS READ. The spec carries a door
        and its measurements; which stock item each cut comes from is decided
        here, from configuration. That is the difference between a calculator
        that asks for a door and one that can ask for any product in the
        catalogue to be booked out of stock.
        """
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except ValueError:
                raise UserError(
                    _("The door calculator's message could not be read. Nothing"
                      " was created.")
                )

        if not isinstance(spec, dict):
            raise UserError(_("The door calculator sent no door."))

        track = (spec.get("track") or "").strip()

        if track not in TRACK_TYPES:
            raise UserError(
                _("“%s” is not a track type this makes orders for.", track or "")
            )

        lift = (spec.get("lift") or "standard").strip()

        if lift not in LIFT_TYPES:
            raise UserError(_("“%s” is not a lift type.", lift))

        parsed = {
            "reference": (spec.get("wo") or "").strip(),
            "mark": (spec.get("mark") or "").strip(),
            "door_qty": int(self._door_wo_number(
                spec.get("qty"), "door_qty", required=False) or 1),
            "track": track,
            "track_size": TRACK_TYPES[track][0],
            "track_label": TRACK_TYPES[track][1],
            "lift": lift,
            "lift_label": LIFT_TYPES[lift],
            "width": self._door_wo_number(spec.get("width"), "width"),
            "height": self._door_wo_number(spec.get("height"), "height"),
            "vertical": self._door_wo_number(spec.get("vertical"), "vertical"),
            "horizontal": self._door_wo_number(spec.get("horizontal"), "horizontal"),
            "hilift": self._door_wo_number(spec.get("hilift"), "hilift", required=False),
            "sections": int(spec.get("sections") or 0),
            "drum": (spec.get("drum") or "").strip(),
            # For the info papers. All optional: an order raised by an older
            # copy of the calculator simply prints fewer rows rather than
            # being refused, because the cut list is the part that matters and
            # it is already complete without these.
            "config": (spec.get("config") or "").strip(),
            "ebf": (spec.get("ebf") or "").strip(),
            "projection": self._door_wo_number(
                spec.get("projection"), "projection", required=False),
            "ftsc": self._door_wo_number(spec.get("ftsc"), "ftsc", required=False),
            "capacity": self._door_wo_number(
                spec.get("capacity"), "capacity", required=False),
            "jb": self._door_wo_jamb_counts(spec.get("jb")),
        }

        # THE CABLES ARE OPTIONAL, because the calculator cannot work them out
        # without a door weight and says so on its own screen. A door sent
        # without a weight is a tracks-only order rather than a refusal.
        cable_type = (spec.get("cable_type") or "").strip()
        matched = [size for size in CABLE_SIZES if size in cable_type]

        if spec.get("cable") and matched:
            parsed["cable"] = self._door_wo_number(spec.get("cable"), "cable")
            parsed["cable_size"] = matched[0]
            parsed["weight"] = self._door_wo_number(
                spec.get("weight"), "weight", required=False)
        elif spec.get("cable") and cable_type:
            raise UserError(
                _("“%s” is not a cable size this makes orders for.", cable_type)
            )
        else:
            parsed["cable"] = 0.0
            parsed["cable_size"] = None
            parsed["weight"] = self._door_wo_number(
                spec.get("weight"), "weight", required=False)

        return parsed

    @api.model
    def _door_wo_jamb_counts(self, raw):
        """{"10": 4, ...} as the calculator DISPLAYED, overrides included.

        Not recomputed from the door height. The calculator carries a per-shop
        override for these, so the number on its screen is not always the
        number its table gives - and a paper that disagrees with the screen it
        was printed from is worse than no paper.
        """
        counts = {}

        if not isinstance(raw, dict):
            return counts

        for size in ("10", "12", "14", "16"):
            value = raw.get("j%s" % size)

            if value in (None, "", False, "--"):
                continue

            try:
                number = int(float(value))
            except (TypeError, ValueError):
                continue

            if 0 <= number <= 99:
                counts[size] = number

        return counts

    @api.model
    def _door_wo_parse_order(self, spec):
        """The whole order: a W/O and the marks on it.

        ONE ORDER PER W/O, NOT PER DOOR. An order carries mark A three times
        and mark B twice, and manufacturing wants one card for that job rather
        than five. Each mark keeps its own measurements, because they are
        different doors.

        The single-door shape is still accepted, as one mark, so that a
        calculator that has not been updated keeps working rather than being
        refused by a newer server.
        """
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except ValueError:
                raise UserError(
                    _("The door calculator's message could not be read. Nothing"
                      " was created.")
                )

        if not isinstance(spec, dict):
            raise UserError(_("The door calculator sent no door."))

        doors = spec.get("doors")

        if not isinstance(doors, list) or not doors:
            parsed = self._door_wo_parse(spec)

            return {"reference": parsed["reference"], "doors": [parsed]}

        if len(doors) > 50:
            raise UserError(
                _("That order has %s marks on it, which is more than this"
                  " makes one manufacturing order for.", len(doors))
            )

        reference = (spec.get("wo") or "").strip()
        out = []

        for index, door in enumerate(doors):
            if not isinstance(door, dict):
                raise UserError(_("Mark %s could not be read.", index + 1))

            door = dict(door)
            door.setdefault("wo", reference)
            parsed = self._door_wo_parse(door)

            if not parsed["mark"]:
                parsed["mark"] = chr(65 + index) if index < 26 else str(index + 1)

            out.append(parsed)

        return {"reference": reference, "doors": out}

    # --- which stock item each cut comes from --------------------------------

    @api.model
    def _door_wo_setting(self, key):
        """The product a setting points at, or an empty recordset."""
        raw = self.env["ir.config_parameter"].sudo().get_param(key)

        if not raw:
            return self.env["product.product"]

        try:
            return self.env["product.product"].browse(int(raw)).exists()
        except (TypeError, ValueError):
            return self.env["product.product"]

    @api.model
    def _door_wo_track_product(self, track_size):
        key = "door_work_order.track_%s_product_id" % track_size.strip('"')

        return self._door_wo_setting(key)

    @api.model
    def _door_wo_cable_product(self, cable_size):
        found = self._door_wo_setting(CABLE_SIZES[cable_size])

        if found:
            return found

        fragment = CABLE_FALLBACK_NAME[cable_size]

        return self.env["product.product"].search(
            [("name", "ilike", fragment)], order="name", limit=1
        )

    @api.model
    def _door_wo_plan(self, parsed):
        """The cut list, and anything missing that must be set up first.

        Returns (items, missing). It REPORTS rather than raises, because the
        review page's job is to show the whole picture at once: a shop that has
        configured neither the track stock nor the cable reel should learn both
        on the first visit rather than one per attempt.
        """
        items = []
        missing = []
        track_product = self._door_wo_track_product(parsed["track_size"])

        if not track_product:
            missing.append(
                _("%s track stock - set it in Manufacturing > Configuration >"
                  " Settings.", parsed["track_size"])
            )

        for role, length, label in [
            ("track_vertical", parsed["vertical"], _("Vertical track")),
            ("track_horizontal", parsed["horizontal"], _("Horizontal track")),
        ]:
            items.append({
                "role": role,
                "label": label,
                "product": track_product,
                "length_inches": length,
                "length_label": self._door_wo_inches_label(length),
                "quantity": 2,
                "note": parsed["track_label"],
            })

        if parsed["cable_size"]:
            cable_product = self._door_wo_cable_product(parsed["cable_size"])

            if not cable_product:
                missing.append(
                    _("%s cable reel - set it in Manufacturing > Configuration"
                      " > Settings.", parsed["cable_size"])
                )

            items.append({
                "role": "cable",
                "label": _("Cable"),
                "product": cable_product,
                "length_inches": parsed["cable"],
                "length_label": self._door_wo_inches_label(parsed["cable"]),
                "quantity": 2,
                "note": "%s%s" % (
                    parsed["cable_size"],
                    parsed["drum"] and (" - drum %s" % parsed["drum"]) or "",
                ),
            })

        return items, missing

    @api.model
    def _door_wo_summary_text(self, parsed):
        lines = [
            _("Door: %(width)s\" x %(height)s\"",
              width=("%g" % parsed["width"]), height=("%g" % parsed["height"])),
            _("Track: %s", parsed["track_label"]),
            _("Lift: %s", parsed["lift_label"]),
        ]

        if parsed["lift"] == "highlift" and parsed["hilift"]:
            lines.append(_("Hi-lift: %s\"", "%g" % parsed["hilift"]))

        if parsed["sections"]:
            lines.append(_("Sections: %s", parsed["sections"]))

        if parsed["weight"]:
            lines.append(_("Door weight: %s lb", "%g" % parsed["weight"]))

        if parsed["drum"]:
            lines.append(_("Drum: %s", parsed["drum"]))

        if not parsed["cable_size"]:
            lines.append(
                _("No cable: the calculator was given no door weight, so this"
                  " order covers the tracks only.")
            )

        return "\n".join(lines)

    # --- raising the order ----------------------------------------------------

    @api.model
    def _door_wo_existing(self, parsed):
        """An order already raised for this door, if there is one.

        A BUTTON GETS PRESSED TWICE. A link that creates a record is going to
        be clicked again - by a double tap, a back button, a refreshed tab - and
        two manufacturing orders for one door is a second door being built. So
        an unfinished order carrying the same W/O and mark is returned instead
        of a new one, and the page says plainly that is what happened.
        """
        reference = parsed.get("reference")

        if not reference:
            return self.browse()

        # KEYED ON THE W/O ALONE, because the order is now the W/O. It used to
        # include the mark, from when one order meant one door; with every mark
        # on a single order, keeping the mark in the key would raise a second
        # order for the same job the moment a different mark happened to be
        # open when the button was pressed.
        return self.search(
            [
                ("door_wo_reference", "=", reference),
                ("state", "in", ("draft", "confirmed", "progress")),
            ],
            order="id desc",
            limit=1,
        )

    @api.model
    def _door_wo_create(self, spec):
        """Raise ONE manufacturing order for a whole W/O. Returns (order, reused)."""
        order = self._door_wo_parse_order(spec)
        existing = self._door_wo_existing(order)

        if existing:
            return existing, True

        planned = []
        missing = []

        for parsed in order["doors"]:
            items, gaps = self._door_wo_plan(parsed)
            planned.append((parsed, items))

            for gap in gaps:
                if gap not in missing:
                    missing.append(gap)

        if missing:
            raise UserError(
                _("This cannot be sent to manufacturing yet, because the"
                  " following is not set up:\n\n%s", "\n".join(missing))
            )

        job_product = self._door_wo_setting("door_work_order.job_product_id")

        if not job_product:
            job_product = self.env.ref(
                "door_work_order.product_door_work_order", raise_if_not_found=False
            )

        if not job_product:
            raise UserError(
                _("No product is set for door work orders. Set one in"
                  " Manufacturing > Configuration > Settings.")
            )

        total_doors = sum(parsed["door_qty"] for parsed, _items in planned)
        labels = [parsed["mark"] for parsed, _i in planned if parsed["mark"]]

        production = self.create({
            "product_id": job_product.id,
            # THE WHOLE JOB. Three of mark A and two of mark B is an order for
            # five doors, and the floor should see five.
            "product_qty": float(total_doors or 1),
            "origin": self._door_wo_origin(order),
            "door_wo_reference": order["reference"] or False,
            "door_wo_mark": ", ".join(labels) or False,
            "door_wo_summary": self._door_wo_order_summary(order, planned),
            "door_wo_mark_ids": [
                (0, 0, {
                    "sequence": (index + 1) * 10,
                    "label": parsed["mark"] or chr(65 + index),
                    "door_qty": parsed["door_qty"],
                    "width": parsed["width"],
                    "height": parsed["height"],
                    "weight": parsed["weight"],
                    "track_label": parsed["track_label"],
                    "config": parsed["config"] or "%s - %s" % (
                        parsed["track_label"], parsed["lift_label"]),
                    "projection": parsed["projection"],
                    "sections": parsed["sections"],
                    "drum": parsed["drum"],
                    "ebf": parsed["ebf"],
                    "capacity": parsed["capacity"],
                    "ftsc": parsed["ftsc"],
                    "cable_type": parsed["cable_size"] or "",
                    "jb_10": parsed["jb"].get("10", 0),
                    "jb_12": parsed["jb"].get("12", 0),
                    "jb_14": parsed["jb"].get("14", 0),
                    "jb_16": parsed["jb"].get("16", 0),
                })
                for index, (parsed, _items) in enumerate(planned)
            ],
        })

        # The cut list is created after the order, not nested inside the marks,
        # because an item carries BOTH its mark and its order and the nested
        # form can only supply one of them.
        for mark, (parsed, items) in zip(production.door_wo_mark_ids, planned):
            for index, item in enumerate(items):
                self.env["door.work.order.item"].create({
                    "production_id": production.id,
                    "mark_id": mark.id,
                    "sequence": (index + 1) * 10,
                    "role": item["role"],
                    "product_id": item["product"].id if item["product"] else False,
                    "length_inches": item["length_inches"],
                    "length_label": item["length_label"],
                    # PIECES FOR THE WHOLE MARK. Two per door, times however
                    # many of that door the order is for - which is the thing
                    # the quantity box never used to change.
                    "quantity": item["quantity"] * parsed["door_qty"],
                    "note": item["note"],
                })

            if self._door_wo_consume_components():
                production._door_wo_add_components(items, parsed["door_qty"])

        return production, False

    @api.model
    def _door_wo_order_summary(self, order, planned):
        """The order in words: every mark, how many, and how big."""
        lines = []

        for parsed, _items in planned:
            lines.append(_(
                "Mark %(mark)s - %(qty)s door(s): %(w)s\" x %(h)s\", %(track)s,"
                " %(lift)s",
                mark=parsed["mark"] or "?", qty=parsed["door_qty"],
                w=("%g" % parsed["width"]), h=("%g" % parsed["height"]),
                track=parsed["track_label"], lift=parsed["lift_label"]))

            if not parsed["cable_size"]:
                lines.append(_(
                    "   no cable: no door weight was given for this mark"))

        return "\n".join(lines)

    def _door_wo_marks_for_report(self):
        """The marks to print, as plain dicts.

        ONE SHAPE FOR THE TEMPLATE. An order raised before marks existed keeps
        its numbers on the order itself, and rather than give the paper two
        ways to read a door - which is how a template quietly starts printing
        one of them wrongly - the old shape is converted here and the template
        sees only this.
        """
        self.ensure_one()

        def jb_pairs(source):
            pairs = [("J-10", source.jb_10), ("J-12", source.jb_12),
                     ("J-14", source.jb_14), ("J-16", source.jb_16)]

            return [p for p in pairs if p[1]]

        if self.door_wo_mark_ids:
            return [{
                "label": mark.label, "door_qty": mark.door_qty,
                "width": mark.width, "height": mark.height,
                "weight": mark.weight, "track_label": mark.track_label,
                "config": mark.config, "projection": mark.projection,
                "sections": mark.sections, "drum": mark.drum, "ebf": mark.ebf,
                "capacity": mark.capacity, "ftsc": mark.ftsc,
                "cable_type": mark.cable_type, "jb": jb_pairs(mark),
                "vertical": mark._door_wo_item_length("track_vertical"),
                "horizontal": mark._door_wo_item_length("track_horizontal"),
                "cable": mark._door_wo_item_length("cable"),
            } for mark in self.door_wo_mark_ids]

        if not self.door_wo_item_ids:
            return []

        return [{
            "label": self.door_wo_mark or "", "door_qty": 1,
            "width": self.door_wo_width, "height": self.door_wo_height,
            "weight": self.door_wo_weight,
            "track_label": self.door_wo_track_label,
            "config": self.door_wo_config, "projection": self.door_wo_projection,
            "sections": self.door_wo_sections, "drum": self.door_wo_drum,
            "ebf": self.door_wo_ebf, "capacity": self.door_wo_capacity,
            "ftsc": self.door_wo_ftsc, "cable_type": self.door_wo_cable_type,
            "jb": jb_pairs(self),
            "vertical": self._door_wo_item_length("track_vertical"),
            "horizontal": self._door_wo_item_length("track_horizontal"),
            "cable": self._door_wo_item_length("cable"),
        }]

    @api.model
    def _door_wo_origin(self, order):
        parts = [p for p in ["Door Calculator", order.get("reference")] if p]

        return " / ".join(parts)

    @api.model
    def _door_wo_consume_components(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "door_work_order.consume_components"
        ) in ("True", "true", "1")

    def _door_wo_add_components(self, items, door_qty=1):
        """Book the stock items onto the order as components.

        OFF UNLESS ASKED FOR. Booking 20 ft off a 500 ft reel means deciding
        whether the shop counts reels, feet or pieces, and nobody has said
        which. Pieces is the only one of the three that is certainly true - two
        cables are two cables - so that is what this books, and the length it
        was cut to stays on the cut list where it can be read.
        """
        self.ensure_one()
        Move = self.env["stock.move"]

        for item in items:
            product = item["product"]

            if not product:
                continue

            # NO `name`: stock.move lost it in 19, and the cut length it would
            # have carried is on the cut list where it belongs anyway.
            Move.create({
                "product_id": product.id,
                "product_uom_qty": item["quantity"] * (door_qty or 1),
                "product_uom": product.uom_id.id,
                "raw_material_production_id": self.id,
                "location_id": self.location_src_id.id,
                "location_dest_id": self.production_location_id.id,
                "company_id": self.company_id.id,
            })
