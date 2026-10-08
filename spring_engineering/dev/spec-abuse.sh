#!/bin/sh
# EVERY FIELD THE CART ROUTE PUTS ON AN ORDER LINE, POSTED HOSTILE.
#
#   sh dev/spec-abuse.sh
#   BASE=https://host sh dev/spec-abuse.sh
#
# WHY THIS EXISTS. /spring-calculator/add-to-cart is public and unauthenticated,
# and the line it creates is read by whoever picks and ships the order. The
# description used to be built by interpolating the caller's own strings, so a
# posted spec could write anything onto it. This is not hypothetical - a single
# request produced an order line reading "Door: 600 lb -- PAID IN FULL, ship
# immediately" and "Discount: 100% approved by manager", on its own lines.
#
# The PRICE was never reachable that way: the server recomputes it from the
# geometry and ignores whatever the browser believes, which dev/price-parity.sh
# checks. This checks the other half, which is that the paperwork cannot be
# forged either. Every case below must be REFUSED, and the legitimate spec at the
# end must still go through - a route that rejects everything would pass the
# first half of this test and be useless.
set -e
cd "$(dirname "$0")/.."

BASE="${BASE:-$ODOO_BUILD_URL}"
GOOD_SPRINGS='[{"role":"Inner","wire":0.2625,"id":3.75,"length":19},{"role":"Outer","wire":0.3125,"id":6,"length":20}]'

post() {
    curl -s -X POST "$BASE/spring-calculator/add-to-cart" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"params\":{\"spec\":$1}}"
}

fail=0

refuse() {
    label="$1"
    body=$(post "$2")
    verdict=$(printf '%s' "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin).get('result', {})
print('refused' if d.get('error') else 'ACCEPTED')")

    if [ "$verdict" = "refused" ]; then
        printf "  %-46s refused\n" "$label"
    else
        printf "  %-46s ACCEPTED - the line can be forged\n" "$label"
        fail=1
    fi
}

echo "hostile specs, all of which must be refused:"
refuse "assembly carries a note" \
    "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex (WARRANTY VOID)\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "spring role carries a newline" \
    "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":[{\"role\":\"Inner\\nNOTE: substitute cheaper wire\",\"wire\":0.2625,\"id\":3.75,\"length\":19},{\"role\":\"Outer\",\"wire\":0.3125,\"id\":6,\"length\":20}]}"
refuse "door weight carries a payment claim" \
    "{\"doorWeight\":\"600 -- PAID IN FULL\",\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "door height carries a discount line" \
    "{\"doorWeight\":600,\"doorHeight\":\"7ft\\nDiscount: 100% approved\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "cycle target is prose" \
    "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":\"as many as you like\",\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "door weight absurd" \
    "{\"doorWeight\":999999,\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "door height absurd" \
    "{\"doorWeight\":600,\"doorHeight\":\"99' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "spring count out of range" \
    "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":99,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}"
refuse "an inside diameter we do not carry" \
    "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":[{\"role\":\"Inner\",\"wire\":0.2625,\"id\":9.5,\"length\":19}]}"
refuse "a length off the quarter-inch grid" \
    "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":10000,\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":[{\"role\":\"Inner\",\"wire\":0.2625,\"id\":3.75,\"length\":19.1}]}"

echo ""
echo "and the legitimate spec must still go through:"
body=$(post "{\"doorWeight\":600,\"doorHeight\":\"7' 0\\\"\",\"cycles\":\"10,000\",\"springs\":2,\"assembly\":\"Duplex\",\"springsSpec\":$GOOD_SPRINGS}")
printf '%s' "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin).get('result', {})
if d.get('error'):
    print('  REFUSED a legitimate spec:', d['error'])
    raise SystemExit(1)
print(f\"  accepted, quoted {d['total']} and booked {d['net']}\")
" || fail=1

if [ "$fail" = "1" ]; then
    echo ""
    echo "AN ORDER LINE CAN BE FORGED BY ITS OWN CALLER - do not ship this." >&2
    exit 1
fi
