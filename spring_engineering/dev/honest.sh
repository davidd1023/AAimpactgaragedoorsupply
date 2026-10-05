#!/bin/sh
# The numbers to quote. One command, so the honest figure cannot drift from
# whatever was last convenient to measure.
#
#   sh dev/honest.sh
#
# IN SAMPLE is what the fitter reproduces of what it was shown. EXTERNAL is two
# independent uniform draws from the allowed box that have never entered the
# fit - that is the figure that predicts a door nobody has quoted yet. The gap
# between them is the overfitting, and it is large: do not quote the first
# number alone.
set -e
cd "$(dirname "$0")/.."

echo "IN SAMPLE"
node dev/replay.mjs 2>&1 | grep -E "byte-identical|verified reading|^  FAIL" | grep -v "^  FAIL" | sed 's/^/  /'
printf "  invariants: %s/13\n" "$(node dev/replay.mjs 2>&1 | grep -c '^  PASS')"

echo ""
echo "EXTERNAL - uniform draws from the allowed box, never fitted"
printf "  %-30s %s\n" "sample" "n     wire     length   within 1\""
for f in dev/eval-rand-seed777001.json dev/eval-soft2-spread.json dev/eval-clean.json; do
    [ -f "$f" ] || continue
    printf "  %-30s %s\n" "$(basename "$f" .json)" \
        "$(node dev/realistic.mjs "$f" 2>&1 | tail -1 | sed 's/everything in the allowed box *//')"
done

echo ""
echo "CLEAN vs FLAGGED - the readings the reference answers without a message"
echo "are the ones that get ordered, so they are scored on their own"
node dev/clean-cases.mjs dev/eval-rand-seed777001.json dev/eval-soft2-spread.json \
    dev/eval-clean.json 2>&1 | head -2 | sed 's/^/  /'

echo ""
echo "SINGLE - external random draw, the reference's own wire fed back"
if [ -f dev/eval-single.json ]; then
    node dev/single-external.mjs dev/eval-single.json | sed 's/^/  /'
fi

echo ""
echo "REFERENCE WARNINGS - agreement reading by reading"
node dev/warn-check.mjs dev/pulled-0*.json dev/pulled-k*.json dev/pulled-a1.json 2>&1 | sed 's/^/  /'
