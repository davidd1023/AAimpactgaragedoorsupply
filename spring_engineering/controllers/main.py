# The calculator on the public website.
#
# WHY A CONTROLLER AT ALL. The module started as a backend app: an
# ir.actions.client plus a menu item, with its assets in web.assets_backend.
# That is reachable only at /odoo/action-..., which IS the backend, so a link
# to it from the website dropped the visitor out of the site and into Odoo.
# There was no frontend route to land on.
import json
import logging
import math
import os
import re

from odoo import http

from ..pricing import (
    CONE_PRICES, FILLER_PRICE_PER_FOOT, FILLER_SPRING_ID, STEEL_PRICE_PER_LB,
)
from odoo.http import request

_logger = logging.getLogger(__name__)

# --- Pricing, read from the calculator rather than copied ------------------
# THE BROWSER'S PRICE IS NEVER TRUSTED. /spring-calculator is public, so the
# figure a page posts back is whatever its sender chose. The price charged is
# computed here, from the specification, using these constants.
#
# They are PARSED out of the calculator's own source instead of being restated,
# because a copy would drift the day someone edits one and not the other - and
# the failure would be a customer quoted one price and charged another, which
# is the worst kind of silent bug. Parsed lazily and loudly: if the shapes ever
# change, adding to the cart fails with a message instead of quietly using a
# stale number, and the storefront stays up either way.
_CALC_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "src", "js", "spring_engineering.js",
)
_prices = None


def _calculator_constants():
    """The supplier costs, plus the steel density read from the component.

    THE COSTS COME FROM pricing.py, not from the JavaScript. They used to be
    parsed out of the component source so that one file held them; that file is
    served to every visitor, so the costs were public and the markup was a
    division away from any quote. See pricing.py.

    THE DENSITY IS STILL READ FROM THE COMPONENT, because the page genuinely uses
    it to show spring weights and the two must not drift: the server charges for
    the same pounds of steel the page displayed. A density is physics and worth
    nothing to a competitor, so there is no reason to hide it and every reason to
    keep one copy.
    """
    global _prices

    if _prices is not None:
        return _prices

    with open(_CALC_JS, encoding="utf-8") as fh:
        src = fh.read()

    found = re.search(r"const STEEL_DENSITY = ([\d.]+);", src)

    if not found:
        raise ValueError("cannot find STEEL_DENSITY in spring_engineering.js")

    # Read once per worker, as before. The density changes about never, and a
    # file read on every add-to-cart is a strange thing to pay for.
    #
    # THE STEEL RATE IS NOT IN HERE. It became a setting, so caching it would
    # serve the old price until the worker restarted - which is exactly the
    # failure the markup's note warns about. It is read per request by
    # _steel_per_lb().
    _prices = {
        "cones": dict(CONE_PRICES),
        "density": float(found.group(1)),
    }

    return _prices




# --- Markup ----------------------------------------------------------------
# THE MARKUP NEVER REACHES THE BROWSER.
#
# What the page is sent is RATES that already include it - a cone price, a price
# per pound - so the figures it shows add up to the figure it charges without
# the percentage itself ever being served. That matters on a public page: an 80%
# markup beside a cost breakdown tells a customer, or a competitor, exactly what
# the springs cost us.
#
# Read fresh on every request rather than cached, so changing the parameter
# takes effect immediately instead of on the next restart.
MARKUP_KEY = "spring_engineering.markup_percent"

# EVERY WORD ON THE ORDER LINE IS CHOSEN HERE, NOT BY THE CALLER.
#
# The description is read by whoever picks and ships the order, and it used to be
# built by interpolating the caller's own strings. A posted spec could therefore
# write anything onto the line, newlines included - a real request to this route
# produced:
#
#     Duplex (WARRANTY VOID), 2 springs
#     Inner
#     NOTE: substitute cheaper wire: 0.2625" wire, ...
#     Door: 600 lb -- PAID IN FULL, ship immediately lb, 7ft
#     Discount: 100% approved by manager, 10,000 cycles
#
# The PRICE was never at risk, because the server recomputes it from the geometry
# and ignores whatever the browser thinks. The paperwork was: a forged line that
# says "paid in full" costs a shipment, not a margin.
#
# Filtering the strings is the wrong fix - it is a guess about what is dangerous.
# The route now parses every descriptive field into a number or a known word and
# renders the line from those, so no caller-supplied text reaches it at all.
ASSEMBLIES = ("Single", "Duplex", "Triplex")
SPRING_ROLES = ("Inner", "Middle", "Outer", "Spring")

# WHAT THE SHOP WILL NOT WIND, however well the calculator sizes it.
#
# Owner, 2026-10-28: "for duplex springs we will leave the option there for
# people who want to use it, but customers will no longer be able to add
# duplex springs to the cart, instead give them a message on the page that
# will say something like we do not currently manufacture custom duplex
# springs."
#
# SEPARATE FROM `ASSEMBLIES`, which says what this code can WORK OUT. The
# calculator still computes a duplex pair, still prices it and still shows the
# figures - that was asked for in the same breath. This says only what may be
# bought, so turning duplex back on is deleting one word rather than finding
# everywhere it was refused.
#
# IN `quote_assembly` RATHER THAN IN THE ROUTE, because the calculator's own
# Add to Cart is not the only way in: the dealer Quick Order prices springs
# through here too, and a spring the shop cannot make is one it cannot make
# for a dealer either. The dealer page shows the refusal as a note against the
# line, which is what it does with every other reason a spring cannot be
# quoted.
UNBUILDABLE_ASSEMBLIES = ("Duplex",)
NOT_MANUFACTURED = (
    "We do not currently manufacture custom %s springs. Please call us on"
    " 786-238-7640 and we will tell you what we can do for this door."
)

# The heaviest door any drum here is rated for is 2200 lb; the ceiling is a sanity
# bound on the text, not an engineering limit, and the reference's own maximum
# cycle target is 350,000.
MAX_DOOR_WEIGHT = 10000
MAX_CYCLES = 1000000


def _as_int(value, low, high):
    """An integer in range, or None. Accepts "10,000" as well as 10000."""
    try:
        parsed = int(round(float(str(value).replace(",", "").strip())))
    except (TypeError, ValueError):
        return None

    return parsed if low <= parsed <= high else None


def _door_height(value):
    """Feet and inches parsed out of the browser's own formatting, or None.

    The page sends `7' 0"`. Anything else is refused rather than passed through:
    this string is going on a document somebody acts on.
    """
    match = re.fullmatch(r"\s*(\d{1,2})\s*'\s*(\d{1,2})\s*\"?\s*", str(value or ""))

    if not match:
        return None

    feet, inches = int(match.group(1)), int(match.group(2))

    if not (0 < feet <= 40 and 0 <= inches < 12):
        return None

    return feet, inches


# The drum names the calculator works in - "CANIMEX/TF D400-144" - plus the
# bare codes the dealer page stores. Letters, digits, spaces and the three
# punctuation marks those names actually use, and nothing else: this string is
# printed on a sticker that goes in a box and on a page a phone opens, so it is
# checked here rather than trusted to whatever posted it.
DRUM_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 /.-]{0,39}")

# No drum needs more turns than this, and a figure past it is a bug rather
# than a door. The reference prints turns to a tenth, so a tenth is kept.
MAX_TURNS = 60.0


def _drum_name(value):
    """The drum a quote was worked out on, or "" if it was not stated."""
    match = DRUM_NAME.fullmatch(str(value or "").strip())

    return match.group(0) if match else ""


def _turns(value):
    """Turns at full wind to a tenth, or 0.0 if the browser did not state them.

    ZERO IS "NOT STATED", which is also what the calculator returns for a
    hi-lift drum it has no turns curve for, and the two mean the same thing
    here: there is no figure to put on the sticker.
    """
    try:
        parsed = round(float(value), 1)
    except (TypeError, ValueError):
        return 0.0

    return parsed if 0 < parsed <= MAX_TURNS else 0.0


def _pricing_param(key):
    """A non-negative number from a system parameter, or ValueError.

    RAISES RATHER THAN FALLING BACK. There is no safe default for either of the
    parameters that use this: a missing markup sells every assembly at cost, and
    a missing labour charge gives the work away, and in both cases nothing about
    the page or the cart would look wrong while it happened. The module ships
    both records, so a missing or unreadable one means it was deleted or edited
    by hand, and the callers turn that into "call us" instead of a price. A lost
    phone call costs less than a month of selling at cost.

    ONE READER FOR BOTH PARAMETERS, deliberately. The markup had its own copy of
    this and the labour charge would have had a second - including a second copy
    of the subtle part below, which is the kind of duplication that has already
    cost this project real bugs twice.
    """
    raw = request.env["ir.config_parameter"].sudo().get_param(key)

    # MISSING IS CHECKED BEFORE float(), not by letting float() complain.
    # get_param returns False when there is no row, and float(False) is 0.0 -
    # a perfectly valid number - so a deleted parameter sailed through the
    # conversion and sold at cost, which is the exact failure this guard exists
    # to prevent. Zero is a legitimate value for either parameter and cannot be
    # told apart from a deleted row after the conversion, which is why the
    # distinction has to be made here.
    if raw is None or raw is False or not str(raw).strip():
        raise ValueError(f"{key} is not set - cannot price an assembly")

    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{key} is {raw!r}, not a number - cannot price an assembly")

    # A negative markup quotes below cost and negative labour pays the customer
    # to take it. Either is a typo, not an instruction.
    if value < 0:
        raise ValueError(f"{key} is {value}, which is below zero")

    return value


def _markup_factor():
    """Cones and the plastic filler are charged at cost: the factor is 1.

    Owner, 2026-10-16: the per-pound setting is the spring's sale price, with
    the steel, the labour and the margin already in it. Cones and filler are
    added on top at what they cost us, with no markup. The markup setting was
    removed from Settings.

    Kept as a function so the calculator, Custom Torsion Spring and the dealer
    Quick Order still take the factor from one place.
    """
    return 1.0


STEEL_KEY = "spring_engineering.steel_per_lb"


def _steel_per_lb():
    """The SELL price of a pound of finished spring, labour included.

    Owner, 2026-10-15: the markup no longer applies to it - it is already a
    selling price. The markup still applies to the cones and the filler.

    A SETTING RATHER THAN A CONSTANT, because steel moves. pricing.py holds the
    default a fresh database starts with; this is the live figure, and like the
    markup it is read fresh on every request so a change takes effect without a
    restart.
    """
    return _pricing_param(STEEL_KEY)


def _labor_flat():
    """No separate labour charge any more (owner, 2026-10-15).

    The steel setting is now the SELL price per pound of finished spring, with
    the labour already in it, so there is nothing to add per assembly. Kept as
    a function returning 0 so the quotes, the page's rates and the dealer
    Quick Order keep their shape.
    """
    return 0.0


def _spec_weight(wire, diameter, length, density):
    """The weight the calculator would compute for one spring.

    Same closed form it uses - density * (pi^2 / 4) * wire * (ID + wire) *
    length, to the cent - which is what lets a submitted weight be CHECKED
    rather than believed.
    """
    volume = (math.pi ** 2) / 4 * wire * (diameter + wire) * length
    return round(density * volume, 2)


# The one real URL. Everything else redirects here, so links, search engines
# and anybody typing it out land on a single canonical address.
CANONICAL = "/spring-calculator"

# WHAT PEOPLE ACTUALLY TYPE. The route is matched exactly - lowercase, hyphen -
# so /spring_calculator, /Spring-Calculator and /spring-engineering were all a
# 404, which is an unhelpful thing to hand someone who is one underscore out.
# A 301 rather than serving the page at several URLs: the content has one
# address, and the alias tells the browser and the crawler so.
ALIASES = [
    "/spring_calculator",
    "/spring-engineering",
    "/spring_engineering",
    "/springcalculator",
    "/spring-springs",
    "/torsion-calculator",
]


def _door_line(width, height, weight, hi_lift, cycles):
    """The door, as one line of the order description.

    EACH PART ONLY IF IT IS KNOWN. A door with no hi-lift says nothing about
    hi-lift rather than saying zero, and a width that could not be read is left
    off - the line describes what the customer gave, and a blank is not a
    measurement.

    THE WORK ORDER SHEET PARSES THIS, so the wording is an interface. It reads
    each fact on its own rather than matching the line as a whole, which is
    what lets an order placed before width and hi-lift existed still print.
    """
    parts = []

    if width:
        parts.append('%d\' %d" wide' % (width[0], width[1]))

    parts.append('%d\' %d" high' % (height[0], height[1]))
    parts.append("%s lb" % weight)

    if hi_lift:
        parts.append('%s" hi-lift' % hi_lift)

    parts.append("{:,} cycles".format(cycles))

    return "Door: " + ", ".join(parts)


def quote_assembly(spec, factor=None):
    """Validate a specification and price it, without touching any order.

    Returns {"error": ...} or the quote that add_assembly_lines books. Shared by
    the public calculator's add-to-cart and by other modules (the dealer Quick
    Order) so a spring is priced and described one way only. `factor` multiplies
    the cones and filler; it defaults to 1 (at cost) and no caller changes it.
    """
    spec = spec or {}

    try:
        prices = _calculator_constants()
        factor = _markup_factor() if factor is None else factor
        labor = _labor_flat()
        per_lb = _steel_per_lb()
    except ValueError:
        _logger.exception("spring_engineering: cannot read pricing constants")

        return {"error": "Pricing is misconfigured - please call us to order."}

    springs = spec.get("springs")

    if not isinstance(springs, int) or not 1 <= springs <= 4:
        return {"error": "That spring count is not one we build."}

    items = spec.get("springsSpec") or []

    if not 1 <= len(items) <= 2:
        return {"error": "An assembly is one spring or a nested pair."}

    assembly = spec.get("assembly")

    if assembly not in ASSEMBLIES:
        return {"error": "That is not an assembly we build."}

    # THE LOCK, of which the page's Contact Us button is only the courtesy.
    # This route is public and takes a posted specification, so "the button
    # was not shown" stops nobody.
    if assembly in UNBUILDABLE_ASSEMBLIES:
        return {"error": NOT_MANUFACTURED % assembly.lower()}

    weight = _as_int(spec.get("doorWeight"), 1, MAX_DOOR_WEIGHT)

    if weight is None:
        return {"error": "That door weight is not one we can work from."}

    height = _door_height(spec.get("doorHeight"))

    if height is None:
        return {"error": "That door height is not one we can work from."}

    cycles = _as_int(spec.get("cycles"), 1, MAX_CYCLES)

    if cycles is None:
        return {"error": "That cycle target is not one we build to."}

    # THE REST OF THE DOOR, for the work order sheet. Neither affects the
    # price, so neither may stop a sale: a width that cannot be read and a
    # hi-lift that is absent are both simply left off the line.
    width = _door_height(spec.get("doorWidth"))
    hi_lift = _as_int(spec.get("hiLift"), 0, 240) or 0

    # THE DRUM AND THE TURNS, for the shop and not for the customer.
    #
    # Both have always been worked out in the browser and both were thrown
    # away here - the drum deliberately (see the description below, where it
    # still does not appear), the turns because nobody had asked for them.
    # The hardware station asks for them now: a winder needs to know how many
    # turns to put on, and which drum the figures were worked out on, and
    # neither is recoverable from a wire size and a length.
    #
    # KEPT AS DATA, NOT AS PROSE, and only in the spec the shop floor reads.
    # The order line the customer sees is unchanged.
    #
    # NEITHER MAY STOP A SALE, like the width and the hi-lift above: a spec
    # from an older page carries no turns, and a hi-lift drum has no turns
    # curve to state them from, so an absent figure is left out rather than
    # printed as a zero somebody has to interpret.
    drum = _drum_name(spec.get("drum"))
    turns = _turns(spec.get("turns"))

    cone_total = 0.0
    steel_weight = 0.0
    filler_inches = 0.0
    lines = []

    for item in items:
        try:
            wire = float(item["wire"])
            diameter = float(item["id"])
            length = float(item["length"])
        except (KeyError, TypeError, ValueError):
            return {"error": "That specification is incomplete."}

        # Lengths come off a quarter-inch grid and the reference refuses
        # anything past 120", so neither is a judgement call.
        if not 0 < length <= 120 or round(length * 4) != length * 4:
            return {"error": f'{length}" is not a length we can wind.'}

        if diameter not in prices["cones"]:
            return {"error": f'{diameter}" is not an inside diameter we carry.'}

        if not 0.1 < wire < 0.7:
            return {"error": f'{wire}" is not a wire size we carry.'}

        role = item.get("role", "Spring")

        if role not in SPRING_ROLES:
            return {"error": "That is not a spring position we build."}

        # Only one ID takes a filler, and it is cut to that spring's length.
        if diameter == FILLER_SPRING_ID:
            filler_inches += length

        cone_total += prices["cones"][diameter]
        steel_weight += _spec_weight(wire, diameter, length, prices["density"])
        lines.append(
            f'{role}: {wire}" wire, {diameter}" ID, {length}" long'
        )

    cones = round(springs * cone_total * factor, 2)
    # Sell price per lb, labour included: NOT marked up (owner, 2026-10-15).
    steel = round(springs * steel_weight * per_lb, 2)

    # PLASTIC FILLER, for the one spring ID that takes it.
    #
    # One per spring, cut to that spring's own length - a 4 ft spring takes
    # 4 ft of filler - so the quantity is feet of material and the price is
    # per foot. Quoted as $19.44 for a 6 ft stock length and $22.68 for 7 ft,
    # which are both exactly $3.24 a foot.
    #
    # It is a supplier cost, so the markup applies, the same as the cones and
    # the steel.
    filler_feet = round(springs * filler_inches / 12.0, 4)
    filler = round(filler_feet * FILLER_PRICE_PER_FOOT * factor, 2)

    # TWO LINES, TWO SUBTOTALS. The filler is its own product on its own
    # line, so the spring line must carry the assembly WITHOUT it - pricing
    # the whole order there and then adding a filler line bills the filler
    # twice. `total` is what the customer pays and what the page quotes;
    # `assembly_total` is what the spring line books - NOT `assembly`, which
    # is the validated assembly name from the spec and was shadowed by an
    # earlier draft of this, putting a dollar figure on the order line where
    # the word Duplex belongs.
    assembly_total = round(cones + steel + labor, 2)
    total = round(assembly_total + filler, 2)

    # A LINE PER ASSEMBLY, created directly rather than through _cart_add.
    # _cart_add looks for an existing line with the same product and adds
    # to its quantity, which is right for a catalogue item and wrong here:
    # every assembly is the same product and a different specification, so
    # two quotes would merge into one line of quantity two and the second
    # specification would be lost.

    description = "\n".join([
        "Custom Torsion Spring Assembly",
        f'{assembly}, {springs} spring{"s" if springs != 1 else ""}',
        *lines,
        # NO DRUM. It is ours to know and not the customer's to read on an
        # order line - and it is recorded on the quote's inputs anyway.
        #
        # Every value here has been through a parser above, so the line is
        # built from integers and words this file chose.
        _door_line(width, height, weight, hi_lift, cycles),
    ])


    # THE SPRING AS DATA, for the shop floor (aa_shop_floor). The description
    # above is for people; the Springs work order is built from this.
    # Hand: half LH, half RH, an odd one goes LH (owner, 2026-10-14). A Duplex
    # inner spring is the same hand as its outer.
    lh = (springs + 1) // 2
    spec_data = {
        "assembly": assembly,
        "springs": springs,
        "lh": lh,
        "rh": springs - lh,
        "items": [
            {
                "role": item.get("role", "Spring"),
                "wire": float(item["wire"]),
                "id": float(item["id"]),
                "length": float(item["length"]),
            }
            for item in items
        ],
        "door": {
            "weight": weight,
            "height": "%s' %s\"" % (height[0], height[1]),
            "cycles": cycles,
        },
    }

    # ABSENT RATHER THAN EMPTY. A spec that cannot say which drum or how many
    # turns says nothing, so the shop floor can tell "nobody worked this out"
    # from "worked out as zero" without a special case for either.
    if drum:
        spec_data["drum"] = drum

    if turns:
        spec_data["turns"] = turns

    return {
        "springs": springs,
        "assembly": assembly,
        "description": description,
        "spec": spec_data,
        # THE DOOR AS NUMBERS, alongside the line of prose above it. The work
        # order sheet reads this rather than parsing the description back:
        # prose has to be interpreted, and anything else in the text that
        # looks like a door - the Drum option is labelled "(up to 530 lb)" -
        # gets interpreted too. A width that could not be read is 0, which is
        # "nobody said" and prints as nothing.
        "door": {
            "width_in": (width[0] * 12 + width[1]) if width else 0,
            "height_in": height[0] * 12 + height[1],
            "weight_lb": weight,
            "hi_lift_in": hi_lift,
            "cycles": "{:,}".format(cycles),
        },
        "assembly_total": assembly_total,
        "total": total,
        "cones": cones,
        "steel": steel,
        "filler": filler,
        "filler_feet": filler_feet,
        "filler_inches": filler_inches,
        "filler_unit": round(FILLER_PRICE_PER_FOOT * factor, 4),
    }


def add_assembly_lines(order, quote, qty=1, note=""):
    """Book a quote from quote_assembly on `order`: the spring line, plus the
    filler line when the spring ID takes one. `qty` assemblies of the same spec.
    Returns {"error": ...} or {"net": what the lines net after tax}.
    """
    assembly_total = quote["assembly_total"]
    filler = quote["filler"]
    filler_feet = quote["filler_feet"]
    filler_inches = quote["filler_inches"]
    springs = quote["springs"]
    description = quote["description"] + (f"\n{note}" if note else "")

    product = request.env.ref(
        "spring_engineering.product_custom_spring", raise_if_not_found=False
    )

    if not product:
        return {"error": "The spring product is missing - please call us to order."}

    # sudo because the product is deliberately unpublished: it is not
    # something to browse to, only something the calculator configures.
    variant = product.sudo().product_variant_id

    # THE SPECIFICATION IS STORED, NOT ONLY DESCRIBED.
    #
    # `name` is a stored computed field and Odoo rebuilds it from the product
    # whenever the line is linked to another one - which is exactly what
    # happens to a spring ordered as a kit option. The whole specification was
    # thrown away a line later, leaving the floor a spring with no wire, no
    # length and no door. Everything below the heading is kept in a field of
    # its own instead, and sale_order_line._compute_name puts it back on every
    # recompute.
    spec_note = "\n".join(description.splitlines()[1:]).strip()

    line = request.env["sale.order.line"].sudo().create({
        "order_id": order.id,
        "product_id": variant.id,
        "name": description,
        "aa_spec_note": spec_note,
        "product_uom_qty": qty,
    })
    line.aa_write_door(quote.get("door") or {})
    # Written after creation: price_unit is computed from the product and
    # the pricelist on create, and the product deliberately lists at zero.
    # The spec travels with the line so a confirmed order can build its
    # Springs work order from data instead of from this description.
    line_values = {"price_unit": assembly_total}
    if quote.get("spec"):
        line_values["spring_spec_json"] = json.dumps(quote["spec"])
    line.write(line_values)
    target = round(assembly_total * qty, 2)

    # WHAT WE RECEIVE HAS TO BE THE PRICE WE COMPUTED, WHATEVER THE TAXES
    # ARE SET TO.
    #
    # `total` is a price to be received: supplier cost, times the markup,
    # plus labour. price_unit is not that figure under every tax
    # configuration. With ordinary tax-excluded taxes the two coincide and
    # the customer pays tax on top. But a company whose sales tax is set up
    # as PRICE-INCLUDED - which is normal in much of the world and is one
    # checkbox away anywhere - makes price_unit the gross, so a 15%
    # included tax would have us book 297.88 on a 342.56 quote and hand the
    # whole margin to the tax authority. Nothing would look wrong: the cart
    # would show exactly the quoted number.
    #
    # Rather than reason about tax types, read back what Odoo itself
    # computed as the net and close the gap.
    #
    # THE CORRECTION IS A RATIO, NOT A DIFFERENCE, and that is the whole
    # trick. Adding the shortfall looks like the obvious move and converges
    # far too slowly, because under an included tax the correction is itself
    # taxed: each pass closes only about 13% of a 15% gap, so reaching half a
    # cent from a 56-dollar shortfall takes about sixty passes. Measured, not
    # reasoned about - four passes left a cent on the table. Scaling by
    # target/net lands exactly in ONE pass for any percentage tax.
    #
    # The additive fallback is kept for the case the ratio cannot handle, a
    # net of zero, and the loop stays for fixed-amount taxes and for two
    # taxes in a chain. The cent nudge stops it spinning when rounding to the
    # currency's precision means no new price_unit can get closer.
    for _ in range(6):
        net = line.price_subtotal
        shortfall = target - net

        if abs(shortfall) < 0.005:
            break

        if net > 0.01:
            candidate = round(line.price_unit * target / net, 2)
        else:
            candidate = round(line.price_unit + shortfall, 2)

        if candidate == line.price_unit:
            candidate = round(line.price_unit + (0.01 if shortfall > 0 else -0.01), 2)

        line.write({"price_unit": candidate})

    # If it still does not reconcile, the line is left as close as it got and
    # the mismatch is logged rather than hidden: a quote that books the wrong
    # amount is worth an entry in the log even though the customer sees the
    # right figure.
    if abs(target - line.price_subtotal) >= 0.005:
        _logger.warning(
            "spring_engineering: quoted %s but the line nets %s after tax "
            "- check the taxes on product_custom_spring",
            target, line.price_subtotal,
        )

    # THE FILLER AS ITS OWN LINE, because it is its own product - the owner
    # buys it separately and it ships alongside. Quantity is FEET, so the
    # line reads as what is actually supplied rather than as a mystery
    # surcharge on the spring.
    filler_net = 0.0

    if filler_feet > 0:
        filler_product = request.env.ref(
            "spring_engineering.product_custom_filler", raise_if_not_found=False
        )

        if not filler_product:
            return {"error": "The filler product is missing - please call us to order."}

        filler_line = request.env["sale.order.line"].sudo().create({
            "order_id": order.id,
            "product_id": filler_product.sudo().product_variant_id.id,
            "name": (
                f'Plastic Filler for {FILLER_SPRING_ID}" spring\n'
                f'{springs} length{"s" if springs != 1 else ""} of '
                f'{round(filler_inches, 2)}", cut to the spring'
            ),
            "product_uom_qty": round(filler_feet * qty, 4),
        })
        filler_line.write({"price_unit": quote["filler_unit"]})
        filler_target = round(filler * qty, 2)

        # Same tax correction as the spring line - see the note there. What
        # we book has to be the price we quoted whatever the taxes are set
        # to, and a per-foot quantity makes the rounding worth checking.
        for _ in range(6):
            net = filler_line.price_subtotal
            shortfall = filler_target - net

            if abs(shortfall) < 0.005:
                break

            if net > 0.01:
                candidate = round(filler_line.price_unit * filler_target / net, 4)
            else:
                candidate = round(filler_line.price_unit + shortfall / (filler_feet * qty), 4)

            if candidate == filler_line.price_unit:
                break

            filler_line.write({"price_unit": candidate})

        filler_net = filler_line.price_subtotal

    return {"net": round(line.price_subtotal + filler_net, 2)}


class SpringEngineeringWebsite(http.Controller):
    # auth="public" so a visitor needs no account, website=True so the request
    # carries the site's theme, menus and language, and sitemap=True so the
    # page is offered to search engines like any other.
    @http.route(
        CANONICAL,
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def spring_calculator(self, **kwargs):
        return http.request.render("spring_engineering.calculator_page", {})

    # sitemap=False so only the canonical URL is offered to crawlers.
    @http.route(ALIASES, type="http", auth="public", website=True, sitemap=False)
    def spring_calculator_aliases(self, **kwargs):
        return request.redirect(CANONICAL, code=301)

    # --- The rates the page prices with --------------------------------------
    @http.route(
        "/spring-calculator/rates",
        type="jsonrpc",
        auth="public",
        website=True,
        methods=["POST"],
    )
    def spring_calculator_rates(self, **kwargs):
        """Cone prices and price per pound, markup already applied.

        The calculator prices as the inputs change, so it needs the rates
        locally - but it does not need, and is not told, the markup. These come
        back marked up, which is all it needs to show a figure that matches
        what the cart will charge.
        """
        try:
            prices = _calculator_constants()
            factor = _markup_factor()
            labor = _labor_flat()
            per_lb = _steel_per_lb()
        except ValueError:
            _logger.exception("spring_engineering: cannot read pricing constants")

            return {"error": "Pricing is misconfigured."}

        # THE LABOUR CHARGE IS SENT; THE MARKUP IS NOT. The difference is not
        # inconsistency, it is what each one is. The page has to show a total
        # that matches what the cart charges, so it needs every number that goes
        # into that total - and the labour charge is one of them. The markup is
        # not a number in the total; it is the policy that produced the rates,
        # and the rates arrive with it already applied.
        #
        # So the labour figure IS inferable from two quotes, because it is the
        # part that does not change with the spring. That is unavoidable for any
        # fee included in a price shown to the person paying it. It is not shown
        # as a line of its own, which is what "not displayed" can mean while the
        # total is still correct; wanting the amount itself unknowable means not
        # quoting a price at all.
        return {
            "cones": {str(d): round(p * factor, 4) for d, p in prices["cones"].items()},
            # Already a sell price (labour included), so not marked up.
            "perLb": round(per_lb, 6),
            "labor": labor,
            # Plastic filler, per foot, for the one spring ID that takes it. The
            # page needs it to quote a total the cart will honour; see the note
            # above about why the labour charge is sent and the markup is not.
            "fillerPerFoot": round(FILLER_PRICE_PER_FOOT * factor, 6),
            "fillerSpringId": FILLER_SPRING_ID,
        }

    # --- Add a configured assembly to the cart ---------------------------
    @http.route(
        "/spring-calculator/add-to-cart",
        type="jsonrpc",
        auth="public",
        website=True,
        methods=["POST"],
    )
    def spring_calculator_add_to_cart(self, spec=None, **kwargs):
        """Create a cart line for one configured assembly.

        The page sends the SPECIFICATION - spring count, and each spring's
        wire, inside diameter and length. Everything chargeable is derived
        here. A sender can therefore ask for a spring the calculator would not
        have recommended, but cannot ask for one at a price it did not earn,
        which is the distinction that matters on a public page.
        """
        quote = quote_assembly(spec or {})

        if quote.get("error"):
            return quote

        # THE CART, OR A NEW ONE. _get_and_cache_current_cart returns an empty
        # recordset when the session has none - it does not create - so the
        # creation is explicit. (website.sale_get_order, which did both, is
        # gone in 19.)
        website = request.website
        order = website._get_and_cache_current_cart() or website._create_cart()

        booked = add_assembly_lines(order, quote)

        if booked.get("error"):
            return booked

        return {
            "total": quote["total"],
            "cones": quote["cones"],
            "steel": quote["steel"],
            "filler": quote["filler"],
            # WHAT THE LINE ACTUALLY BOOKS, net of tax. Equal to `total` when
            # everything is right, and reported so that dev/price-parity.sh can
            # check the whole chain - the page quotes it, the server computes it,
            # and the order line nets it - rather than only the first two.
            "net": booked["net"],
            "cart_quantity": order.cart_quantity,
        }
