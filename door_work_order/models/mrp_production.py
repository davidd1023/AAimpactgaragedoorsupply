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
    door_wo_item_count = fields.Integer(compute="_compute_door_wo_item_count")

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
        if not parsed["reference"]:
            return self.browse()

        return self.search(
            [
                ("door_wo_reference", "=", parsed["reference"]),
                ("door_wo_mark", "=", parsed["mark"] or False),
                ("state", "in", ("draft", "confirmed", "progress")),
            ],
            order="id desc",
            limit=1,
        )

    @api.model
    def _door_wo_create(self, spec):
        """Raise one manufacturing order for one door. Returns (order, reused)."""
        parsed = self._door_wo_parse(spec)
        existing = self._door_wo_existing(parsed)

        if existing:
            return existing, True

        items, missing = self._door_wo_plan(parsed)

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

        production = self.create({
            "product_id": job_product.id,
            "product_qty": 1.0,
            "origin": self._door_wo_origin(parsed),
            "door_wo_reference": parsed["reference"] or False,
            "door_wo_mark": parsed["mark"] or False,
            "door_wo_summary": self._door_wo_summary_text(parsed),
            "door_wo_item_ids": [
                (0, 0, {
                    "sequence": (index + 1) * 10,
                    "role": item["role"],
                    "product_id": item["product"].id if item["product"] else False,
                    "length_inches": item["length_inches"],
                    "length_label": item["length_label"],
                    "quantity": item["quantity"],
                    "note": item["note"],
                })
                for index, item in enumerate(items)
            ],
        })

        if self._door_wo_consume_components():
            production._door_wo_add_components(items)

        return production, False

    @api.model
    def _door_wo_origin(self, parsed):
        parts = [p for p in ["Door Calculator", parsed["reference"], parsed["mark"]] if p]

        return " / ".join(parts)

    @api.model
    def _door_wo_consume_components(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "door_work_order.consume_components"
        ) in ("True", "true", "1")

    def _door_wo_add_components(self, items):
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
                "product_uom_qty": item["quantity"],
                "product_uom": product.uom_id.id,
                "raw_material_production_id": self.id,
                "location_id": self.location_src_id.id,
                "location_dest_id": self.production_location_id.id,
                "company_id": self.company_id.id,
            })
