"""WHAT THE BOX IS FOR: one card per hardware kit, and a sticker that carries it.

The hardware station packs a box. Everything about the door that box is for -
the spring it will be hung on, the turns to wind it to, the drum the figures
came off, the finish, the lift, the cable and the track - is on the sale order
in six different places, and none of them is the kit line the packer is looking
at. So the packer either knows the order by heart or goes and asks.

This is that answer, assembled once and shown three ways: a button beside Start
on the Hardware card, a sticker printed for the box, and the page that sticker's
QR code opens on a phone. All three read `aa_hardware_card`, so they cannot
disagree.

ONE DOOR PER CARD (owner, 2026-10-19). A dealer order carries several doors and
each one has its own kit, its own springs and its own cable; mixing two doors'
figures onto one card is how the wrong spring goes in the wrong box. What
belongs to which door is settled by _aa_door_split below.

NOTHING IS INVENTED. A fact that is not on the order is left out - no "n/a", no
zero standing in for a figure nobody worked out. A card with nothing to say does
not appear at all, and neither does its button.
"""

import json
import logging
import re
from urllib.parse import quote, urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import hmac

from .mrp_production import (
    id_label,
    inches_label,
    qty_label,
    wire_label,
)
from .res_config_settings import DEFAULT_STICKER_SIZE, STICKER_SIZES
from .sale_order import is_hardware_kit

_logger = logging.getLogger(__name__)

# The calculator names a drum for its maker, the shop names it for its size:
# "CANIMEX/TF D400-144" is the D400-144 everybody here asks for.
DRUM_MAKER = re.compile(r"^\s*CANIMEX\s*/\s*TF\s*", re.I)

# Which attribute carries the finish. Spelled four ways across the catalogue
# because the kit templates were not all built on the same day.
COLOUR_ATTRIBUTES = ("finish color", "finish colour", "color", "colour")

# A lift cable line, however the catalogue spells the rest of the name.
CABLE_NAME = re.compile(r"\blift\s*cable\b", re.I)

# Any track, for the lines whose name the two exact patterns do not match.
TRACK_NAME = re.compile(r"\btrack\b", re.I)

# TURNS AT FULL WIND, PER DRUM, for an order whose spec never stored them
# (owner, 2026-10-28: "turns must be there"). Orders priced before the
# calculator posted its turns carry the spring but not the turns, and the
# bench still has to wind it. These are the SAME coefficients the calculator
# uses - `DRUMS[...].turnsCurve` in spring_engineering.js - so the card says
# what the calculator would have said: 7' on a D400-96 is 7.9, as S00041
# stored. Standard lift only; a high-lift door is worked out on other curves
# and gets no guess.
#     turns = a*H + b + c/H + d/H^2 + e/H^3 + f/H^4      (H in feet)
DRUM_TURNS = {
    "D400-96": (0.926270103, 1.182458766, 1.622498182,
                1.457531341, 3.164283001, 5.912155063),
    "D400-144": (0.918018474, 1.224217309, 0.903742416,
                 6.136653231, -11.978871764, 24.691717891),
    "D525-216": (0.702285693, 0.936356104, 0.999506286,
                 3.138832124, -3.937059973, 13.452757892),
}

# Below this the curve's inverse powers take over; the calculator clamps too.
TURNS_MIN_FEET = 3.0

DRUM_SIZE = re.compile(r"\bD\s*(\d{3})\s*-\s*(\d+)\b", re.I)
HEIGHT_TEXT = re.compile(r"(\d+(?:\.\d+)?)\s*'\s*(?:(\d+(?:\.\d+)?)\s*\")?")


def drum_turns(drum, height_in):
    """Turns at full wind for a standard-lift door, or 0 if unknown."""
    match = DRUM_SIZE.search(drum or "")
    curve = match and DRUM_TURNS.get("D%s-%s" % match.groups())

    if not curve or not height_in:
        return 0.0

    height = max(float(height_in) / 12.0, TURNS_MIN_FEET)
    a, b, c, d, e, f = curve

    return (a * height + b + c / height + d / height ** 2
            + e / height ** 3 + f / height ** 4)


def height_inches(text):
    """7' 0" -> 84.0, or 0 when the text says no height."""
    match = HEIGHT_TEXT.search(text or "")

    if not match:
        return 0.0

    return float(match.group(1)) * 12 + float(match.group(2) or 0)


def feet_label(inches):
    """108 -> 9' 0", 100.5 -> 8' 4 1/2". How a door is spoken.

    THE SHOP TALKS IN FEET, and so does every other document this order
    touches: the dealer note writes W 9' 0" x H 7' 0" and the calculator asks
    for the height that way. A card that answered 108" would be the only thing
    on the bench that did.
    """
    inches = float(inches or 0)
    feet = int(inches // 12)
    rest = inches - feet * 12

    if not feet:
        return inches_label(rest)

    return "%d' %s" % (feet, inches_label(rest))


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # --- the card -------------------------------------------------------------

    aa_hardware_card = fields.Text(
        string="Hardware Card (data)", compute="_compute_aa_hardware_card",
        help="Everything the hardware station needs to know about the door this "
             "box is for: spring and turns, drum, finish, lift, cable and track.")

    aa_box_url = fields.Char(
        string="Box sticker link", compute="_compute_aa_box_url",
        help="What the sticker's QR code opens. The link is the key, so it is "
             "kept from anybody the box's own figures are kept from.")

    aa_box_url_warning = fields.Char(
        string="Sticker host", compute="_compute_aa_box_url")

    @api.depends("aa_station_kind")
    def _compute_aa_box_url(self):
        # THE HOST IN THE LINK IS A SETTING, AND IT WAS WRONG ON PRODUCTION.
        #
        # Owner, 2026-10-28: *"the link it takes me to is:
        # https://aaimpactgaragedoorsupply.com/box/131/571e5b68..."* - and
        # that apex domain is not Odoo at all. It answers ten bytes of
        # text/plain "Not Found" to everything, `/web/login` included, and it
        # does not redirect. His Odoo is at **www.**aaimpactgaragedoorsupply
        # .com, where that very link returns the box page. One missing `www`
        # against three days of "the sticker leads to a not found page".
        #
        # NOTHING IN THE CODE WAS WRONG. The job, the token, the route and
        # the sticker were all right; `web.base.url` was the apex.
        #
        # AND IT CAN DRIFT BACK. Unless `web.base.url.freeze` is set, Odoo
        # REWRITES `web.base.url` to whichever host an administrator last
        # signed in from - so one sign-in on a bare domain, an odoo.sh build
        # URL or an IP silently repoints every sticker printed afterwards. A
        # QR code cannot be proof-read, which is the whole reason this went
        # unexplained: the fault is invisible until somebody holds a phone up
        # to a box.
        #
        # So the host is shown next to the link, with a warning when it is
        # free to move. Not a correction - this cannot know which host is
        # right, and guessing a `www` onto it would be the same mistake in
        # the other direction.
        frozen = self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url.freeze")

        for production in self:
            kit = production.aa_station_kind == "kit" and production.id
            production.aa_box_url = production._aa_box_url() if kit else ""
            production.aa_box_url_warning = ""

            if not kit:
                continue

            host = urlsplit(production.aa_box_url or "").netloc or _("not set")

            if frozen and frozen not in ("0", "False", "false"):
                # AN ADMINISTRATOR HAS SAID WHICH HOST IS RIGHT, so that is
                # the one, whoever prints and from wherever.
                production.aa_box_url_warning = _(
                    "Every sticker is printed pointing at %s (fixed).", host)
            else:
                # UNFROZEN, so the label follows whoever prints it - which is
                # the host in THIS address bar, and therefore the host this
                # line is being read through. Saying it plainly beats a
                # warning: it is the behaviour, not a fault.
                production.aa_box_url_warning = _(
                    "Printed from here, the sticker will point at %s - a"
                    " sticker follows the address of whoever prints it."
                    " Printed in the background it uses web.base.url"
                    " instead; fix that under Manufacturing > Settings >"
                    " Sticker QR links.", host)

    # NOT STORED, like the two Overview boards. The card is read when somebody
    # asks for it - a tap, a print, a scan - and it is assembled from eight
    # fields on four other records, so a stored copy would be a copy that can
    # be out of date the moment any of them is corrected.
    @api.depends(
        "aa_station_kind", "aa_sale_line_id", "product_id", "product_qty",
        "aa_sale_line_id.order_id.order_line.product_uom_qty",
        "aa_sale_line_id.order_id.order_line.spring_spec_json",
        "aa_sale_line_id.order_id.order_line.name",
        "aa_sale_line_id.order_id.order_line.linked_line_id",
    )
    def _compute_aa_hardware_card(self):
        """ONE ODD ORDER MUST NOT TAKE THE BOARD DOWN WITH IT.

        Every card on the Shop Floor is read in one request, so anything this
        raises for one job stops the whole page rendering - which is how it
        showed up on production: an Owl error with "Component is destroyed"
        underneath and nothing naming the real cause. A card is a convenience;
        the board is the work. So a job whose order cannot be read leaves its
        card empty, says so in the log, and lets the rest of the floor load.
        """
        for production in self:
            try:
                card = production._aa_hardware_card()
            except Exception:
                _logger.exception(
                    "aa_shop_floor: the hardware card for %s could not be "
                    "worked out", production.display_name)
                card = {}

            production.aa_hardware_card = json.dumps(card) if card else False

    def _aa_hardware_card(self):
        """The whole card as plain data, or {} when there is nothing to say.

        {} MEANS NO BUTTON. "If there isn't any hardware in the order don't
        display anything" (owner, 2026-10-19), and a kit whose order says
        nothing about any of the six facts is the same case: a card listing a
        heading and no figures is worse than no card.
        """
        self.ensure_one()

        if self.aa_station_kind != "kit":
            return {}

        kit = self.aa_sale_line_id

        if not kit:
            return {}

        order = kit.order_id
        by_kit, loose = self._aa_door_split(order)
        lines = by_kit.get(kit, self.env["sale.order.line"])
        doors = list(by_kit)
        rows = self._aa_card_rows(kit, lines)
        also = self._aa_card_rows(kit.browse(), loose) if loose else []

        if not rows and not also:
            return {}

        notes = dict(self._aa_line_notes(kit))
        card = {
            "order": self.aa_wo_number or order.aa_wo_number or order.name or self.origin or "",
            "customer": order.partner_id.name or "",
            "kit": (self.product_id.product_tmpl_id.name or "").replace(
                " Hardware Kit", ""),
            # The door the box is for, which is the heading everything under
            # it belongs to. Left out when the order never said.
            "size": self._aa_card_door(kit, notes),
            "weight": self._aa_card_weight(kit, notes,
                                           self._aa_card_specs(lines)),
            "rows": rows,
            "also": also,
        }

        # WHICH DOOR OF HOW MANY, and only when there is more than one. On a
        # single-door order "Door 1 of 1" is noise; on a four-door order it is
        # the whole point of the card.
        #
        # AND ONLY WHEN THIS KIT IS ONE OF THEM. doors.index(kit) raises
        # ValueError when it is not, which is not hypothetical: a job carries
        # aa_station_kind "kit" from the day it was made, and the product on
        # its line can stop looking like a hardware kit afterwards - renamed,
        # swapped, or a template retitled. The read of this field then raised
        # for that one job and took the WHOLE Shop Floor down with it, because
        # every card on the board is read in one go. Found on production,
        # 2026-10-19, as "Component is destroyed".
        if len(doors) > 1 and kit in doors:
            card["door"] = "Door %d of %d" % (doors.index(kit) + 1, len(doors))

        return card

    # --- which lines belong to which door -------------------------------------

    def _aa_door_split(self, order):
        """({kit line: its lines}, lines that belong to no kit).

        TWO RULES, THE STRICTER ONE FIRST. The dealer Quick Order links a
        door's extras to its kit line (linked_line_id), which is a fact rather
        than a guess, so it wins. Anything else - a kit and a spring put in a
        cart by hand - falls back to the rule this module already uses for
        boxing lift cables: a line belongs to the closest kit ABOVE it, which
        is the order the pages that build these orders write them in.

        Lines above the first kit belong to no door. They are still on the
        order and still want saying, so they come back separately rather than
        being attached to a door they may have nothing to do with.
        """
        lines = order.order_line.sorted(lambda line: (line.sequence, line.id))
        empty = self.env["sale.order.line"]
        by_kit = {}

        for line in lines:
            if is_hardware_kit(line.product_id):
                by_kit[line] = empty

        loose = empty
        current = None

        for line in lines:
            if line in by_kit:
                current = line
                continue

            if self._aa_card_ignores(line):
                continue

            owner = line.linked_line_id if line.linked_line_id in by_kit else current

            if owner:
                by_kit[owner] |= line
            else:
                loose |= line

        return by_kit, loose

    def _aa_card_ignores(self, line):
        """Lines that can hold none of the six facts."""
        if line.display_type or line.product_uom_qty <= 0 or not line.product_id:
            return True

        if getattr(line, "is_delivery", False):
            return True

        # A knurled stud is hardware, and it is not one of the six facts. The
        # fasteners spring_engineering adds under a bracket would otherwise
        # have to be read past on every card.
        return bool(line.track_prep_role)

    # --- the six facts --------------------------------------------------------

    def _aa_card_rows(self, kit, lines):
        """[(label, value)] for one door: only what the order actually says."""
        notes = dict(self._aa_line_notes(kit)) if kit else {}
        specs = self._aa_card_specs(lines)
        rows = []

        # THE OWNER'S OWN ORDER, as he listed them: spring and turns, drum,
        # colour, cable, then the track's lift and lengths. The door itself is not one of the six -
        # it is the heading the six belong to - so it is in the card above
        # rather than in this list.
        # THE LIFT SITS WITH THE TRACK (owner, 2026-10-28: "tracks lift type
        # and lengths"): the lift is a fact about the track, so the two read
        # together at the bottom. "Hardware Color" the same day - plain
        # "Color" left the packer asking colour of what.
        drum = self._aa_card_drum(kit, specs, notes)
        lift = self._aa_card_lift(kit, notes, lines)

        for label, value in (
            *self._aa_card_spring_rows(lines, specs, kit, drum, lift),
            ("Drum", drum),
            ("Hardware Color", self._aa_card_colour(kit)),
            ("Cable", self._aa_card_cable(lines)),
            ("Track Lift", lift),
            ("Track", self._aa_card_track(lines)),
        ):
            if value:
                rows.append([label, value])

        return rows

    @staticmethod
    def _aa_card_specs(lines):
        """The spring specifications on these lines, as (line, spec) pairs."""
        specs = []

        for line in lines:
            if not line.spring_spec_json:
                continue

            try:
                spec = json.loads(line.spring_spec_json)
            except ValueError:
                continue

            if isinstance(spec, dict) and spec.get("items"):
                specs.append((line, spec))

        return specs

    def _aa_card_spring_rows(self, lines, specs, kit=None, drum="", lift=""):
        """The spring, written the way the shop writes it, and its turns.

        A DUPLEX PAIR IS TWO ROWS, because it is two springs wound to one
        specification and the inner one has its own wire and its own length.
        """
        rows = []

        for line, spec in specs:
            items = spec["items"]
            quantity = line.product_uom_qty or 1.0

            for item in items:
                label = "Spring"

                if len(items) > 1:
                    label = "Spring (%s)" % (item.get("role") or "spring").lower()

                rows.append((label, '%s wire · %s I.D. · %s long' % (
                    wire_label(item["wire"]), id_label(item["id"]),
                    inches_label(item["length"]))))

            turns = spec.get("turns") or self._aa_card_turns(
                line, spec, kit, drum, lift)

            if turns:
                # To a tenth, which is what the reference prints and what the
                # calculator showed whoever priced this order.
                rows.append(("Turns", "%s at full wind" % qty_label(
                    round(float(turns), 1))))

            hands = []

            for hand, key in (("LH", "lh"), ("RH", "rh")):
                count = (spec.get(key) or 0) * quantity

                if count:
                    hands.append("%s %s" % (qty_label(count), hand))

            if hands:
                rows.append(("Wind", ", ".join(hands)))

        if not rows:
            # A stock spring carries no specification, but its code is the
            # specification: SPR-2625-2.625-R.
            for line in lines:
                code = line.product_id.default_code or ""

                if code.startswith("SPR-"):
                    rows.append(("Spring", line.product_id.with_context(
                        display_default_code=False).display_name))

        return rows

    def _aa_card_turns(self, line, spec, kit, drum, lift):
        """Turns worked out from the drum and door height, for a spec that
        never stored them. Standard lift only - see DRUM_TURNS."""
        if lift and lift != "Standard":
            return 0.0

        if line.aa_door_hi_lift_in:
            return 0.0

        door = spec.get("door") if isinstance(spec.get("door"), dict) else {}
        height = (
            (kit and kit.aa_door_height_in)
            or line.aa_door_height_in
            or height_inches(door.get("height") or spec.get("doorHeight"))
        )

        return drum_turns(spec.get("drum") or drum, height)

    def _aa_card_drum(self, kit, specs, notes):
        """The drum the spring figures were worked out on.

        THE SPRING'S OWN DRUM FIRST. The owner asked for "the drum used in
        calculation", and that is the one the calculator was set to when it
        sized this spring - now carried in the spec. The kit's own drum option
        and the line note are the same drum in every order we have seen, and
        they are what an order placed before the spec carried it has.
        """
        for _line, spec in specs:
            if spec.get("drum"):
                return DRUM_MAKER.sub("", spec["drum"]).strip()

        # aa_dealer_orders' own field, when that module is installed.
        if kit and "aa_drum" in kit._fields and kit.aa_drum:
            return kit.aa_drum

        return (notes.get("Drum") or "").strip()

    def _aa_card_colour(self, kit):
        """White or Black, off the kit's own finish option."""
        if not kit:
            return ""

        values = kit.product_id.product_template_attribute_value_ids \
            | kit.product_no_variant_attribute_value_ids

        for value in values:
            if (value.attribute_id.name or "").strip().lower() in COLOUR_ATTRIBUTES:
                return value.name or ""

        # Kits built before the finish was an option carry it in the name.
        name = kit.product_id.display_name or ""

        for word in ("Black", "White"):
            if re.search(r"\b%s\b" % word, name, re.I):
                return word

        return ""

    def _aa_card_lift(self, kit, notes, lines):
        """Standard, or high lift and how much of it."""
        note = (notes.get("Lift") or "").strip()

        if note:
            return note

        if kit and "aa_lift_type" in kit._fields and kit.aa_lift_type:
            if kit.aa_lift_type == "highlift":
                return "High Lift %s" % inches_label(kit.aa_high_lift or 0)

            return "Standard"

        # A calculator spring knows the lift it was sized for: the hi-lift
        # figure is sent as 0 for a standard door and the door height is only
        # there at all when somebody entered it, so this says nothing about an
        # order where nobody did.
        for line in lines:
            if not line.aa_door_height_in:
                continue

            if line.aa_door_hi_lift_in:
                return "High Lift %s" % inches_label(line.aa_door_hi_lift_in)

            return "Standard"

        return ""

    def _aa_cable_cut_inches(self, product):
        """How long each cable of a prepared pair is cut, in inches, or 0.

        The reel quantity on the pair's own kit BoM is for the PAIR, so one
        cable is half of it.
        """
        bom = self.env["mrp.bom"].sudo()._bom_find(
            product, bom_type="phantom").get(product)
        reel = bom and bom.bom_line_ids.filtered(
            lambda line: "reel" in (line.product_id.name or "").lower())[:1]

        if not reel:
            return 0.0

        uom = (reel.product_uom_id.name or "").lower()
        inches_per_unit = 1.0 if uom in ("in", "inch", "inches") else 12.0
        feet = reel.product_qty * inches_per_unit / 12.0

        return feet * 12.0 / 2.0 / (bom.product_qty or 1.0)

    def _aa_card_cable(self, lines):
        """The lift cable, and how long each one is cut."""
        said = []

        for line in lines:
            name = line.product_id.product_tmpl_id.name or ""

            if not CABLE_NAME.search(name):
                continue

            each = self._aa_cable_cut_inches(line.product_id)
            size = re.search(r"Lift Cable\s+(\S+)", name, re.I)
            label = size.group(1) if size else line.product_id.display_name

            if each:
                said.append("%s - %s x %s" % (
                    label, qty_label(2 * line.product_uom_qty),
                    inches_label(each)))
            else:
                # A cut length nobody set is not a cut length to print.
                said.append(label)

        return " · ".join(said)

    def _aa_card_track(self, lines):
        """Every track on the door, with its length."""
        said = []

        for line in lines:
            product = line.product_id.with_context(display_default_code=False)
            name = (product.display_name or "").strip()

            # A PREPARED CABLE IS NAMED FOR THE TRACK IT SUITS - "Lift Cable
            # 1/8" Pair - Prepared (7' Door, 3" Track (15R))" - so the loose
            # read for the word "track" below found the cable and printed it
            # as a third track. Each fact is said once, by the part that owns
            # it.
            if CABLE_NAME.search(name):
                continue

            # READ OFF THE VARIANT, the same way the bench card does: a
            # track's size and length moved out of its name when the tracks
            # were folded into one product per size and type (owner,
            # 2026-10-23). _aa_track_facts reads either shape.
            facts = line.product_id._aa_track_facts()

            if facts:
                said.append('%s" %s %g"' % (
                    facts["size"], facts["kind"].title(), facts["length"]))
            elif TRACK_NAME.search(name):
                said.append(name)

        return " · ".join(said)

    def _aa_card_door(self, kit, notes):
        """The door itself: width by height."""
        if kit and kit.aa_door_width_in and kit.aa_door_height_in:
            return "%s x %s" % (feet_label(kit.aa_door_width_in),
                                feet_label(kit.aa_door_height_in))

        return (notes.get("Door") or "").strip()

    def _aa_card_weight(self, kit, notes, specs):
        """What the door weighs, which is what the spring was sized for."""
        if kit and kit.aa_door_weight_lb:
            return "%s lb" % qty_label(kit.aa_door_weight_lb)

        note = (notes.get("Weight") or "").strip()

        if note:
            return note

        for _line, spec in specs:
            weight = (spec.get("door") or {}).get("weight")

            if weight:
                return "%s lb" % qty_label(float(weight))

        return ""

    # --- the sticker ----------------------------------------------------------

    def _aa_box_token(self):
        """The secret half of this box's link.

        DERIVED, NOT STORED. The same work order always produces the same
        token, so a sticker printed today still opens tomorrow, and there is
        nothing to generate, migrate or leak out of a database column. It
        cannot be guessed without the database secret, and knowing one box's
        token says nothing about any other.
        """
        self.ensure_one()

        # TWENTY-FOUR CHARACTERS OF IT, which is 96 bits - more than enough
        # that nobody will find a box by typing, and 40 characters shorter
        # than the full digest. The length matters because the whole link goes
        # into a QR code that has to be read off a 1 1/4 inch label if the
        # owner chooses one: every character is more modules in the same
        # square, and a denser code is a code a phone gives up on. Truncating
        # an HMAC is sound - the standard allows it, well below this.
        return hmac(self.env(su=True), "aa_shop_floor.box", (self.id,))[:24]

    def _aa_box_url(self):
        """The whole link the QR code holds."""
        self.ensure_one()

        return "%s/box/%d/%s" % (
            self._aa_sticker_base_url(), self.id, self._aa_box_token())

    def _aa_sticker_base_url(self):
        """WHICH SITE A SCANNED STICKER OPENS - and it is no longer a setting.

        THE HOST WAS THE WHOLE FAULT. Owner, 2026-10-28, three times over,
        ending with the link itself: his stickers carried
        `aaimpactgaragedoorsupply.com`, the apex, which Odoo.sh redirects to
        `www` **for `/` only, dropping the path** - so the domain looks
        perfectly healthy typed into a browser and 404s every deep path,
        which is all a sticker QR is. `web.base.url` was the apex, and that
        parameter lives behind Settings > Technical, which does not appear
        without developer mode (*"i dont see any technical option in the
        settings"*).

        So THE PERSON PRINTING THE LABEL DECIDES IT, without knowing they
        have: a sticker printed from a browser carries the address THAT
        BROWSER IS ON. Which is right by construction - somebody is looking
        at Odoo through it, so it serves Odoo, so the sticker opens. No
        setting to find, nothing to type, and nothing to get wrong.

        **ONLY WHILE THE BASE URL IS UNFROZEN**, which is the line this does
        not cross. `web.base.url.freeze` is an administrator SAYING which
        host is the right one, and being overruled by whoever last pressed
        Print would be worse than the fault. Unfrozen, Odoo is already
        rewriting that parameter to whichever host an admin last signed in
        from - so reading the request is the very same policy, applied per
        label instead of per login, and strictly more accurate.

        Nothing printed in the BACKGROUND has a request to read - a cron, a
        shell, a scheduled batch - and those fall back to the parameter,
        which is why it still matters and still gets shown in Settings.
        """
        self.ensure_one()
        params = self.env["ir.config_parameter"].sudo()
        frozen = params.get_param("web.base.url.freeze")
        base = (self.get_base_url() or "").rstrip("/")

        if frozen and frozen not in ("0", "False", "false"):
            return base

        host = request and (request.httprequest.host_url or "").rstrip("/")

        return host or base

    # --- what the sticker is printed on ---------------------------------------
    #
    # THE SIZE IS A SETTING (see res_config_settings): the owner has not
    # settled on label stock yet, so the label reads its own size and lays
    # itself out to fit. A 4 x 6 is the baseline every proportion below is
    # written against.

    STICKER_BASE_WIDTH_MM = 102.0
    STICKER_BASE_HEIGHT_MM = 152.0

    # A label is not a billboard and not a postage stamp. These only catch a
    # typed figure that cannot be meant - a 0 that would make wkhtmltopdf fail
    # outright, or a 400 that would waste a ream finding out.
    STICKER_MIN_INCHES = 1.0
    STICKER_MAX_INCHES = 18.0

    @api.model
    def _aa_sticker_inches(self):
        """(width, height) of the chosen label, in inches."""
        param = self.env["ir.config_parameter"].sudo()
        size = param.get_param("aa_shop_floor.sticker_size") or "4x6"

        if size == "custom":
            width = param.get_param("aa_shop_floor.sticker_width_in")
            height = param.get_param("aa_shop_floor.sticker_height_in")
        else:
            # The key IS the size: "2.25x1.25" is two and a quarter by one and
            # a quarter, so there is no second table to fall out of step.
            width, _sep, height = size.partition("x")

        def inches(value, fallback):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return fallback

            if not number:
                return fallback

            return min(max(number, self.STICKER_MIN_INCHES),
                       self.STICKER_MAX_INCHES)

        return inches(width, 4.0), inches(height, 6.0)

    @api.model
    def _aa_sticker_apply_size(self):
        """Write the chosen size onto the sticker's own paper format.

        RUN FROM THE SETTING AND FROM EVERY MODULE UPDATE, because the setting
        is the truth and the format record is only how wkhtmltopdf is told
        about it. A format shipped in a data file would otherwise put the
        owner's choice back to 4 x 6 the next time the module was updated.
        """
        paperformat = self.env.ref(
            "aa_shop_floor.paperformat_hardware_sticker", raise_if_not_found=False)

        if not paperformat:
            return

        width, height = self._aa_sticker_inches()
        page_width = int(round(width * 25.4))
        page_height = int(round(height * 25.4))

        # A LABEL PRINTER HAS NO UNPRINTABLE BORDER to allow for, and on a
        # small label a 3mm margin all round is a tenth of the sticker, so the
        # smaller the stock the less is given away.
        margin = 3 if min(width, height) >= 3 else 1

        paperformat.sudo().write({
            # Portrait, always, with the real numbers: an orientation that
            # swapped them would mean the layout below had to guess which way
            # round the page was.
            "format": "custom",
            "orientation": "Portrait",
            "page_width": page_width,
            "page_height": page_height,
            "margin_top": margin,
            "margin_bottom": margin,
            "margin_left": margin,
            "margin_right": margin,
        })

        # TOLD TO FORGET THE OLD SIZE. print_page_width and print_page_height
        # are computed WITHOUT @api.depends in core, so writing page_width
        # does not invalidate them and anything that read them earlier in the
        # same transaction keeps the previous answer - which here means a
        # label laid out for the size that has just been replaced. A test
        # holds this: it chose two sizes in a row and the type never changed.
        paperformat.invalidate_recordset(
            ["print_page_width", "print_page_height"])

    # A LABEL HAS TO STAY READABLE. Below about 7pt the figures stop being
    # readable at arm's length on a bench, so the type stops shrinking there
    # and the label shows fewer rows instead - which is what a small sticker
    # is for: enough to know the box, and a code for the rest.
    MIN_ROOT_PT = 7.0
    BASE_ROOT_PT = 11.0
    MM_TO_PT = 2.8346

    # THE SMALLEST QR STILL WORTH PRINTING. At 16mm a link this long lays out
    # at roughly 0.4mm per module, which is about the floor for a phone camera
    # on a thermal print - and on a 1 1/4 inch label there is physically
    # nowhere else for it to go. The upper bound is so a big label does not
    # turn into a code with a caption.
    QR_MIN_MM = 16.0
    QR_MAX_MM = 32.0

    @api.model
    def aa_sticker_sizes(self):
        """The sizes to offer beside Print sticker, and the one in use.

        ASKED FOR AT THE PRINTER (owner, 2026-10-19). The Settings page is
        where a size is configured once; this is where somebody standing at
        the label printer with a different roll in it changes it. Same
        setting, same system parameter - there is no second place the answer
        can live.
        """
        param = self.env["ir.config_parameter"].sudo()
        current = param.get_param(
            "aa_shop_floor.sticker_size") or DEFAULT_STICKER_SIZE
        options = [[value, label] for value, label in STICKER_SIZES
                   if value != "custom"]

        # A SIZE TYPED IN SETTINGS IS STILL THE SIZE IN USE, so it has to be
        # in the list and selected - otherwise opening this would silently
        # show 4 x 6 as the current stock and the next print would change it.
        if current == "custom":
            width, height = self._aa_sticker_inches()
            options.append(["custom", "Custom - %g x %g in" % (width, height)])

        return {"current": current, "options": options}

    @api.model
    def aa_set_sticker_size(self, size):
        """Change the label stock from the Shop Floor. Returns what is in use.

        ONLY THE SIZES ON THE LIST. The parameter is written with raised
        rights - a worker at a bench cannot write system parameters, and
        should not be given a way to write any of them - so what may be
        written here is checked against the offered values rather than
        trusted. "custom" is not one of them: there is nothing in a dialog
        footer to type two inch figures into, so a custom size stays
        Settings' business and is left exactly as it was.
        """
        if not self.env.user.has_group("mrp.group_mrp_user"):
            raise AccessError(_(
                "Only somebody who works in Manufacturing can change the "
                "sticker size."))

        allowed = {value for value, _label in STICKER_SIZES if value != "custom"}

        if size in allowed:
            self.env["ir.config_parameter"].sudo().set_param(
                "aa_shop_floor.sticker_size", size)
            self._aa_sticker_apply_size()

        return self.aa_sticker_sizes()

    def _aa_sticker_layout(self, card=None):
        """How to lay the label out on the stock the owner has chosen.

        TWO THINGS GIVE, IN THIS ORDER: the type shrinks to the smallest size
        still worth printing, and then the list shortens. A fixed template
        does neither, so changing the paper under it either wastes four
        fifths of a 4 x 6 or runs a 4 x 2 onto a second label - and a second
        label for one box is worse than a short one, because only one of them
        ends up on the box.

        NOTHING IS DROPPED SILENTLY. The template says how many rows it left
        out, and the code on the label is the way to read them.
        """
        self.ensure_one()
        report = self.env.ref(
            "aa_shop_floor.action_report_hardware_sticker",
            raise_if_not_found=False)
        paperformat = report.paperformat_id if report else None
        width = paperformat and paperformat.print_page_width or self.STICKER_BASE_WIDTH_MM
        height = paperformat and paperformat.print_page_height or self.STICKER_BASE_HEIGHT_MM
        margin = paperformat.margin_top if paperformat else 3

        scale = min(width / self.STICKER_BASE_WIDTH_MM,
                    height / self.STICKER_BASE_HEIGHT_MM)
        # Not bigger than the design on a sheet of letter paper: the sticker
        # stays a sticker and leaves the rest of the page white.
        scale = min(max(scale, self.MIN_ROOT_PT / self.BASE_ROOT_PT), 1.0)
        root = round(self.BASE_ROOT_PT * scale, 2)

        # The code is worth more than the tenth row, so on a short label it
        # keeps its size while the list gives way - but it never takes more
        # than its share of the height either.
        qr_mm = min(max(min(width * 0.30, height * 0.45), self.QR_MIN_MM),
                    self.QR_MAX_MM)

        # WHAT WILL FIT, in points. The heading sits beside the code, so the
        # block costs whichever of the two is taller; the door size is a band
        # of its own when the order knows the door; and each row is one line
        # plus the air around it.
        usable = (height - 2 * margin) * self.MM_TO_PT
        heading = max(qr_mm * self.MM_TO_PT, root * 3.4)
        banner = root * 2.4 if (card or {}).get("size") or (card or {}).get("weight") else 0.0
        # Room kept back for the "and N more" line and for the rounding
        # wkhtmltopdf does on the way to whole dots.
        slack = root * 1.6
        row = root * 1.62
        fits = int(max((usable - heading - banner - slack) // row, 1))

        return {
            "root": root,
            "qr": round(qr_mm * self.MM_TO_PT, 1),
            "scale": scale,
            "rows": fits,
        }

    def _aa_box_qr_src(self, size=240):
        """The <img src> that draws this box's QR code.

        Built here rather than in the template because the value is a URL -
        slashes, a colon and a query of its own - and it has to be quoted
        before it is put inside another one.
        """
        self.ensure_one()

        return "/report/barcode/?barcode_type=QR&value=%s&width=%d&height=%d" % (
            quote(self._aa_box_url(), safe=""), size, size)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # THE CARD IS THE MANUFACTURING ORDER'S, and the Hardware station shows
    # work orders, so the station's cards read it through here - exactly as
    # they already read aa_shop_spec.
    aa_hardware_card = fields.Text(
        related="production_id.aa_hardware_card", string="Hardware Card (data)")
    aa_box_url = fields.Char(
        related="production_id.aa_box_url", string="Box sticker link")
