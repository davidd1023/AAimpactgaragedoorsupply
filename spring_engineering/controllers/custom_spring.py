# Custom Torsion Spring: the customer already has the specs of the spring that
# broke and only wants an exact match. Nothing to engineer - we work out the
# steel weight, the cones for that I.D. (and the filler a 5 1/4" spring takes)
# and book it to the cart with the same pricing and the same order line as the
# calculator, through quote/add helpers in main.py.
import logging

from odoo import http
from odoo.http import request

from ..pricing import FILLER_PRICE_PER_FOOT, FILLER_SPRING_ID
from .main import (
    _calculator_constants, _labor_flat, _markup_factor, _spec_weight,
    _steel_per_lb, add_assembly_lines,
)

_logger = logging.getLogger(__name__)

CANONICAL = "/custom-torsion-spring"

# Nominal wire code, as written in the COIL-<code>-<ID>-<L/R> product codes,
# to the real diameter the steel weight is worked from.
WIRE_DIAMETERS = {
    "243": 0.2437, "250": 0.2500, "262": 0.2625, "273": 0.2730, "283": 0.2830,
    "289": 0.2890, "295": 0.2950, "306": 0.3065, "312": 0.3125, "319": 0.3195,
    "331": 0.3310, "343": 0.3437, "362": 0.3625, "375": 0.3750, "379": 0.3790,
    "393": 0.3938, "406": 0.4062,
}
ID_LABELS = {"2.625": '2 5/8"', "3.75": '3 3/4"', "5.25": '5 1/4"'}
WINDS = {"LH": "LH", "RH": "RH", "PAIR": "1 LH + 1 RH"}
MAX_QTY = 20


def stocked_combos():
    """{I.D. code: [wire codes]} for every coil we hold in both LH and RH."""
    codes = set(request.env["product.product"].sudo().search(
        [("default_code", "=like", "COIL-%")]).mapped("default_code"))
    combos = {}
    for code in sorted(codes):
        parts = code.split("-")  # COIL-243-2.625-R
        if len(parts) != 4 or parts[3] != "R":
            continue
        wire, inner = parts[1], parts[2]
        if wire in WIRE_DIAMETERS and inner in ID_LABELS and f"COIL-{wire}-{inner}-L" in codes:
            combos.setdefault(inner, []).append(wire)
    return dict(sorted(combos.items(), key=lambda kv: float(kv[0])))


def quote_custom(spec):
    """Price a matched spring. Returns {"error": ...} or a quote add_assembly_lines books.

    Same formula as the calculator: (steel + cones + filler) x markup, then the
    flat labour, once per order line.
    """
    spec = spec or {}
    wire_code, inner, wind = str(spec.get("wire", "")), str(spec.get("id", "")), str(spec.get("wind", ""))
    try:
        length = float(spec.get("length"))
        qty = int(spec.get("qty"))
    except (TypeError, ValueError):
        return {"error": "Enter the spring length and quantity."}

    if wire_code not in stocked_combos().get(inner, []):
        return {"error": "We don't stock that wire / I.D. combination."}
    if wind not in WINDS:
        return {"error": "Choose LH, RH or a pair."}
    if not 0 < length <= 120 or round(length * 4) != length * 4:
        return {"error": 'Length must be in quarter inches, up to 120".'}
    if not 1 <= qty <= MAX_QTY:
        return {"error": f"Quantity must be between 1 and {MAX_QTY}."}

    try:
        prices = _calculator_constants()
        factor = _markup_factor()
        labor = _labor_flat()
        per_lb = _steel_per_lb()
    except ValueError:
        _logger.exception("spring_engineering: cannot read pricing constants")
        return {"error": "Pricing is misconfigured - please call us to order."}

    wire = WIRE_DIAMETERS[wire_code]
    diameter = float(inner)
    if diameter not in prices["cones"]:
        return {"error": "No cone set is configured for that I.D."}

    springs = qty * (2 if wind == "PAIR" else 1)
    weight_each = _spec_weight(wire, diameter, length, prices["density"])
    filler_inches = length if diameter == FILLER_SPRING_ID else 0.0

    cones = round(springs * prices["cones"][diameter] * factor, 2)
    steel = round(springs * weight_each * per_lb * factor, 2)
    filler_feet = round(springs * filler_inches / 12.0, 4)
    filler = round(filler_feet * FILLER_PRICE_PER_FOOT * factor, 2)
    assembly_total = round(cones + steel + labor, 2)
    total = round(assembly_total + filler, 2)

    length_txt = f"{length:g}"
    unit_txt = f"{qty} pair{'s' if qty > 1 else ''}" if wind == "PAIR" else f"{qty} {wind}"
    description = "\n".join([
        "Custom Torsion Spring Assembly (matched spring)",
        f'{unit_txt} - {springs} spring{"s" if springs != 1 else ""}',
        f'.{wire_code} wire, {ID_LABELS[inner]} ID, {length_txt}" long',
    ])

    # The spring as data, for the Springs work order (aa_shop_floor).
    spec_data = {
        "assembly": "Single",
        "springs": springs,
        "lh": qty if wind in ("LH", "PAIR") else 0,
        "rh": qty if wind in ("RH", "PAIR") else 0,
        "items": [{"role": "Spring", "wire": wire, "id": diameter, "length": length}],
    }
    return {
        "springs": springs,
        "description": description,
        "spec": spec_data,
        "assembly_total": assembly_total,
        "total": total,
        "cones": cones,
        "steel": steel,
        "labor": labor,
        "weight": round(weight_each * springs, 2),
        "filler": filler,
        "filler_feet": filler_feet,
        "filler_inches": filler_inches,
        "filler_unit": round(FILLER_PRICE_PER_FOOT * factor, 4),
    }


class CustomTorsionSpringWebsite(http.Controller):

    @http.route(CANONICAL, type="http", auth="public", website=True, sitemap=True)
    def custom_torsion_spring(self, **kwargs):
        combos = stocked_combos()
        return request.render("spring_engineering.custom_torsion_spring_page", {
            "combos": combos,
            "id_labels": ID_LABELS,
        })

    @http.route(CANONICAL + "/quote", type="jsonrpc", auth="public", website=True, methods=["POST"])
    def custom_torsion_spring_quote(self, spec=None, **kwargs):
        quote = quote_custom(spec)
        if quote.get("error"):
            return quote
        return {k: quote[k] for k in ("springs", "weight", "cones", "steel", "labor", "filler", "total")}

    @http.route(CANONICAL + "/add-to-cart", type="jsonrpc", auth="public", website=True, methods=["POST"])
    def custom_torsion_spring_add_to_cart(self, spec=None, **kwargs):
        quote = quote_custom(spec)  # always re-priced here; nothing priced in the browser is trusted
        if quote.get("error"):
            return quote
        website = request.website
        order = website._get_and_cache_current_cart() or website._create_cart()
        booked = add_assembly_lines(order, quote)
        if booked.get("error"):
            return booked
        return {"total": quote["total"]}
