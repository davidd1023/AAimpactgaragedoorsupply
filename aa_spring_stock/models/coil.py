"""Which coil a spring is cut from, and which piece of it.

Coils are products COIL-<wire>-<I.D.>-<L/R> (COIL-262-2.625-R), kept in inches,
one lot per physical piece. Pieces live in three places under the warehouse
stock: Rack (leftover cut pieces), Floor (coils in use) and Boxes (unopened).
Each numbered box is its own location under Boxes (AAM/Stock/Boxes/Box 3).
"""

# Nominal wire code -> real diameter (same table as spring_engineering's
# custom_spring.py). The calculator sends the diameter; the coil code carries
# the nominal three digits.
WIRE_CODES = {
    "243": 0.2437, "250": 0.2500, "262": 0.2625, "273": 0.2730, "283": 0.2830,
    "289": 0.2890, "295": 0.2950, "306": 0.3065, "312": 0.3125, "319": 0.3195,
    "331": 0.3310, "343": 0.3437, "362": 0.3625, "375": 0.3750, "379": 0.3790,
    "393": 0.3938, "406": 0.4062,
}
ID_CODES = {2.625: "2.625", 3.75: "3.75", 5.25: "5.25"}
ID_LABELS = {"2.625": '2 5/8"', "3.75": '3 3/4"', "5.25": '5 1/4"'}

# Where a spring is cut from, best first (owner, 2026-10-19): a leftover piece
# if one is long enough, then the coils on the floor, and the boxes last.
SOURCES = ("Rack", "Floor", "Boxes")

# A full coil as it comes from the supplier, in inches.
FULL_COIL = 84.0


def place_of(location):
    """'Rack', 'Floor' or 'Boxes' for a location or one inside it (Box 3), else None."""
    while location:
        if location.name in SOURCES:
            return location.name
        location = location.location_id
    return None


def wire_code(wire):
    """0.2625 -> '262'. None when no coil wire is within 0.002"."""
    try:
        wire = float(wire)
    except (TypeError, ValueError):
        return None
    code, diameter = min(WIRE_CODES.items(), key=lambda kv: abs(kv[1] - wire))
    return code if abs(diameter - wire) <= 0.002 else None


def id_code(diameter):
    try:
        return ID_CODES.get(round(float(diameter), 4))
    except (TypeError, ValueError):
        return None


def coil_code(wire, diameter, hand):
    """The default_code of the coil a spring is cut from, or None."""
    w, d = wire_code(wire), id_code(diameter)
    if not w or not d or hand not in ("L", "R"):
        return None
    return "COIL-%s-%s-%s" % (w, d, hand)


def spring_cuts(spec, qty=1.0):
    """Every spring to cut for one order line, as dicts.

    LH / RH in the spec are per unit of the order line. A Duplex is a full set
    per hand: the inner spring has the same hand as its outer.
    """
    items = (spec or {}).get("items") or []
    cuts = []
    for hand, count in (("L", spec.get("lh") or 0), ("R", spec.get("rh") or 0)):
        count = int(round(float(count) * (qty or 1.0)))
        for _n in range(count):
            for item in items:
                cuts.append({
                    "role": item.get("role") or "Spring",
                    "hand": hand,
                    "wire": item.get("wire"),
                    "id": item.get("id"),
                    "length": float(item.get("length") or 0.0),
                    "code": coil_code(item.get("wire"), item.get("id"), hand),
                })
    return cuts


def pick_piece(pieces, length):
    """The piece to cut `length` inches from.

    pieces: [(source, available_inches, lot_name, key)] - source is one of
    SOURCES. Returns the chosen tuple or None. In each source the shortest piece
    that is long enough wins: on the Rack that leaves the smallest scrap, on the
    Floor it finishes an opened coil before starting a fuller one.
    """
    for source in SOURCES:
        fits = [p for p in pieces if p[0] == source and p[1] + 1e-6 >= length]
        if fits:
            return min(fits, key=lambda p: (p[1], p[2] or ""))
    return None
