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
    global _prices

    if _prices is not None:
        return _prices

    with open(_CALC_JS, encoding="utf-8") as fh:
        src = fh.read()

    def one(pattern, name):
        found = re.search(pattern, src)

        if not found:
            raise ValueError(f"cannot find {name} in spring_engineering.js")

        return float(found.group(1))

    cones_block = re.search(r"const CONE_PRICES = \{(.*?)\};", src, re.S)

    if not cones_block:
        raise ValueError("cannot find CONE_PRICES in spring_engineering.js")

    cones = {
        float(d): float(p)
        for d, p in re.findall(r"([\d.]+):\s*([\d.]+)", cones_block.group(1))
    }

    if not cones:
        raise ValueError("CONE_PRICES parsed empty")

    _prices = {
        "per_lb": one(r"const STEEL_PRICE_PER_LB = ([\d.]+);", "STEEL_PRICE_PER_LB"),
        "density": one(r"const STEEL_DENSITY = ([\d.]+);", "STEEL_DENSITY"),
        "cones": cones,
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
LABOR_KEY = "spring_engineering.labor_flat"


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
    """What the supplier cost is multiplied by to reach the selling price."""
    return 1.0 + _pricing_param(MARKUP_KEY) / 100.0


def _labor_flat():
    """The labour charge on one assembly, in currency, already a selling price.

    FLAT PER ASSEMBLY, NOT PER SPRING. Fitting a set of springs is one job
    whether it holds one spring or four, which is what "flat" means here and
    what the figure it replaces always did.

    ADDED AFTER THE MARKUP, not multiplied by it. The markup turns a supplier
    cost into a price; this is already a price - what the labour is sold for -
    so marking it up would be marking up a margin. If the intent is ever the
    other way round, this is the one line that has to change.
    """
    return round(_pricing_param(LABOR_KEY), 2)


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
            "perLb": round(prices["per_lb"] * factor, 6),
            "labor": labor,
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
        spec = spec or {}

        try:
            prices = _calculator_constants()
            factor = _markup_factor()
            labor = _labor_flat()
        except ValueError:
            _logger.exception("spring_engineering: cannot read pricing constants")

            return {"error": "Pricing is misconfigured - please call us to order."}

        springs = spec.get("springs")

        if not isinstance(springs, int) or not 1 <= springs <= 4:
            return {"error": "That spring count is not one we build."}

        items = spec.get("springsSpec") or []

        if not 1 <= len(items) <= 2:
            return {"error": "An assembly is one spring or a nested pair."}

        cone_total = 0.0
        steel_weight = 0.0
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

            cone_total += prices["cones"][diameter]
            steel_weight += _spec_weight(wire, diameter, length, prices["density"])
            lines.append(
                f'{item.get("role", "Spring")}: {wire}" wire, {diameter}" ID, {length}" long'
            )

        cones = round(springs * cone_total * factor, 2)
        steel = round(springs * steel_weight * prices["per_lb"] * factor, 2)
        total = round(cones + steel + labor, 2)

        product = request.env.ref(
            "spring_engineering.product_custom_spring", raise_if_not_found=False
        )

        if not product:
            return {"error": "The spring product is missing - please call us to order."}

        # sudo because the product is deliberately unpublished: it is not
        # something to browse to, only something the calculator configures.
        variant = product.sudo().product_variant_id

        # THE CART, OR A NEW ONE. _get_and_cache_current_cart returns an empty
        # recordset when the session has none - it does not create - so the
        # creation is explicit. (website.sale_get_order, which did both, is
        # gone in 19.)
        website = request.website
        order = website._get_and_cache_current_cart() or website._create_cart()

        # A LINE PER ASSEMBLY, created directly rather than through _cart_add.
        # _cart_add looks for an existing line with the same product and adds
        # to its quantity, which is right for a catalogue item and wrong here:
        # every assembly is the same product and a different specification, so
        # two quotes would merge into one line of quantity two and the second
        # specification would be lost.

        description = "\n".join([
            "Custom Torsion Spring Assembly",
            f'{spec.get("assembly", "Single")}, {springs} spring'
            f'{"s" if springs != 1 else ""}',
            *lines,
            # NO DRUM. It is ours to know and not the customer's to read on an
            # order line - and it is recorded on the quote's inputs anyway.
            f'Door: {spec.get("doorWeight", "?")} lb, {spec.get("doorHeight", "?")}'
            f', {spec.get("cycles", "?")} cycles',
        ])

        line = request.env["sale.order.line"].sudo().create({
            "order_id": order.id,
            "product_id": variant.id,
            "name": description,
            "product_uom_qty": 1,
        })
        # Written after creation: price_unit is computed from the product and
        # the pricelist on create, and the product deliberately lists at zero.
        line.write({"price_unit": total})

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
            shortfall = total - net

            if abs(shortfall) < 0.005:
                break

            if net > 0.01:
                candidate = round(line.price_unit * total / net, 2)
            else:
                candidate = round(line.price_unit + shortfall, 2)

            if candidate == line.price_unit:
                candidate = round(line.price_unit + (0.01 if shortfall > 0 else -0.01), 2)

            line.write({"price_unit": candidate})

        # If it still does not reconcile, the line is left as close as it got and
        # the mismatch is logged rather than hidden: a quote that books the wrong
        # amount is worth an entry in the log even though the customer sees the
        # right figure.
        if abs(total - line.price_subtotal) >= 0.005:
            _logger.warning(
                "spring_engineering: quoted %s but the line nets %s after tax "
                "- check the taxes on product_custom_spring",
                total, line.price_subtotal,
            )

        return {
            "total": total,
            "cones": cones,
            "steel": steel,
            # WHAT THE LINE ACTUALLY BOOKS, net of tax. Equal to `total` when
            # everything is right, and reported so that dev/price-parity.sh can
            # check the whole chain - the page quotes it, the server computes it,
            # and the order line nets it - rather than only the first two.
            "net": line.price_subtotal,
            "cart_quantity": order.cart_quantity,
        }
