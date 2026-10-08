#!/bin/sh
# Does the server charge what the page quotes?
#
#   sh dev/price-parity.sh            (uses $ODOO_BUILD_URL)
#   BASE=https://host sh dev/price-parity.sh
#
# WHY THIS EXISTS. The page computes a price for the customer to read and the
# controller computes one to charge, because a public page's figure is whatever
# its sender chose. Two computations of one number is exactly the shape that
# drifts, and the failure is silent and the worst kind: a customer quoted one
# price and charged another.
#
# The controller already parses its constants out of the calculator's source
# rather than restating them, so they cannot diverge. This checks the whole
# path end to end anyway - geometry in, price out, both sides - because that is
# the claim, not the constants.
set -e
cd "$(dirname "$0")/.."
BASE="${BASE:-$ODOO_BUILD_URL}"

if [ -z "$BASE" ]; then
    echo "set BASE or ODOO_BUILD_URL" >&2
    exit 1
fi

# THE RATES COME FROM THE SERVER NOW, so the harness has to be handed them -
# it has no browser and no session, and without them priceAvailable is false
# and the page would quote nothing. Fetching them here is also part of the
# check: if the endpoint and the cart ever disagree about the markup, the
# totals below stop matching.
curl -s -X POST "$BASE/spring-calculator/rates" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"call","params":{}}' \
    | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin)['result']))" \
    > /tmp/parity-rates.json

node --input-type=module - <<'JS' > /tmp/parity-specs.jsonl
import { load, make } from "./dev/harness.mjs";
import { readFileSync } from "node:fs";
const rates = JSON.parse(readFileSync("/tmp/parity-rates.json", "utf8"));
const mod = await load();
// One of each shape that can reach the cart: Single at each priced diameter,
// both real Duplex pairs, and an alias - which must price as the pair it is
// engineered as, not its nameplate.
const cases = [
    { assembly: "Single", springId: '2 5/8"', springs: 1, drum: "CANIMEX/TF D400-96", radius: "15", weight: "300", doorHeightFeet: 7, cycles: "10,000" },
    { assembly: "Single", springId: '3 3/4"', springs: 2, drum: "CANIMEX/TF D400-144", radius: "15", weight: "500", doorHeightFeet: 8, cycles: "25,000" },
    { assembly: "Single", springId: '5 1/4"', springs: 4, drum: "CANIMEX/TF D525-216", radius: "12", weight: "900", doorHeightFeet: 10, cycles: "50,000" },
    { assembly: "Duplex", springId: '3 3/4" inside 6"', springs: 2, drum: "CANIMEX/TF D400-144", radius: "15", weight: "600", doorHeightFeet: 7, cycles: "10,000" },
    { assembly: "Duplex", springId: '2 5/8" inside 5 1/4"', springs: 3, drum: "CANIMEX/TF D525-216", radius: "LHR", weight: "700", doorHeightFeet: 9, cycles: "15,000" },
    { assembly: "Duplex", springId: '3 1/2" inside 5 1/2" (Raynor)', springs: 4, drum: "CANIMEX/TF D525-216", radius: "15", weight: "1100", doorHeightFeet: 12, cycles: "100,000" },
];
for (const st of cases) {
    const c = make(mod, st);
    // Through the app's own normaliser, so this exercises the same key
    // handling the browser does rather than a second reading of the JSON.
    c.rates = mod.normaliseRates(rates);
    if (st.assembly === "Single") {
        const w = c.recommendedWire;
        if (w !== null && w !== undefined) c.state.wireSize = `${w}"`;
    }
    if (!c.resultsVisible) { console.log(JSON.stringify({ skip: st.springId })); continue; }
    console.log(JSON.stringify({ label: `${st.assembly} ${st.springId} x${st.springs}`, spec: c.cartSpec, page: c.priceTotal }));
}
JS

fail=0
while read -r row; do
    label=$(printf '%s' "$row" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('label') or 'skipped '+str(d.get('skip')))")
    spec=$(printf '%s' "$row" | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps(d['spec']) if 'spec' in d else '')")

    if [ -z "$spec" ]; then
        printf "  %-42s %s\n" "$label" "no results, nothing to price"
        continue
    fi

    page=$(printf '%s' "$row" | python3 -c "import sys,json;print(json.load(sys.stdin)['page'])")
    answer=$(curl -s -X POST "$BASE/spring-calculator/add-to-cart" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"params\":{\"spec\":$spec}}")
    server=$(printf '%s' "$answer" \
        | python3 -c "import sys,json;d=json.load(sys.stdin).get('result',{});print(d.get('total', d.get('error','no answer')))")
    # AND WHAT THE ORDER LINE NETS, which is the end of the chain and the only
    # figure that is actually money. It differs from the quote when the product's
    # taxes are price-INCLUDED, because then price_unit is a gross - a config
    # away from handing the whole margin to the tax authority with the cart still
    # showing the quoted number.
    net=$(printf '%s' "$answer" \
        | python3 -c "import sys,json;d=json.load(sys.stdin).get('result',{});print(d.get('net','-'))")

    # NUMERICALLY, not as text: the page prints 1360 where the server prints
    # 1360.0, and a string compare called that a disagreement.
    if python3 -c "import sys;sys.exit(0 if abs(float('$page')-float('$server'))<5e-3 else 1)" 2>/dev/null; then
        if python3 -c "import sys;sys.exit(0 if abs(float('$server')-float('$net'))<5e-3 else 1)" 2>/dev/null; then
            printf "  %-42s page %-10s server %-10s net %-10s ok\n" "$label" "$page" "$server" "$net"
        else
            printf "  %-42s page %-10s server %-10s net %-10s NET DIFFERS\n" "$label" "$page" "$server" "$net"
            fail=1
        fi
    else
        printf "  %-42s page %-10s server %-10s DIFFER\n" "$label" "$page" "$server"
        fail=1
    fi
done < /tmp/parity-specs.jsonl

if [ "$fail" = "1" ]; then
    echo ""
    echo "QUOTED AND CHARGED PRICES DISAGREE - do not ship this." >&2
    exit 1
fi
