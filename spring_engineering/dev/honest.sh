#!/bin/sh
# The numbers to quote. One command, so the honest figure cannot drift from
# whatever was last convenient to measure.
#
#   sh dev/honest.sh
#
# THE ORDER OF THIS OUTPUT IS THE POINT. It runs from the figure that predicts
# a door nobody has quoted yet to the figure that only says the fitter
# remembers what it was shown:
#
#   1. VALIDATION - a uniform draw taken after the last knob was tuned. No
#      choice in this repository has been made against it. This is the number
#      to quote, and it is the lowest.
#   2. TUNED SAMPLES - uniform draws too, but LINE_SLACK (twice), LEVEL_SUPPORT
#      and SPLIT_MIN_SIDE were all set against them, which makes them partly
#      in-sample for those knobs. They read several points high for that
#      reason, not because the model is better than section 1 says.
#   3. IN SAMPLE - what the fitter reproduces of its own training data. It
#      says nothing about a new door; it is here to catch a regression.
#
# This script used to lead with section 3 and leave section 1 out, which is
# how 98.6% got quoted for a model that was really at 90%.
set -e
cd "$(dirname "$0")/.."

# TWO never-tuned draws, scored SEPARATELY and never pooled.
#
# One clean yardstick is enough to measure with and not enough to decide with.
# Every time a choice is checked against the only clean sample, a little of its
# independence is spent - and this session spent some, on whether two held-out
# batches belonged in the fit. The second draw exists so that kind of question
# has somewhere to go that is not the figure being quoted.
#
# They stay separate because the interesting case is DISAGREEMENT. Two draws from
# the same box that read a point apart say the sampling error is about a point,
# which is a thing worth knowing before celebrating half of one. Pooling them
# hides exactly that.
VALIDATION=dev/eval-validation-seed61006.json
VALIDATION2=dev/eval-validation2-seed20261007.json

echo "VALIDATION - never tuned against, these are the figures to quote"
if [ -f "$VALIDATION" ]; then
    printf '  seed 61006:\n'
    node dev/clean-cases.mjs "$VALIDATION" 2>&1 | head -2 | sed 's/^/    /'
else
    echo "  $VALIDATION is missing - there is no honest figure without it" >&2
    exit 1
fi

if [ -f "$VALIDATION2" ]; then
    printf '  seed 20261007:\n'
    node dev/clean-cases.mjs "$VALIDATION2" 2>&1 | head -2 | sed 's/^/    /'
fi

echo ""
echo "ORDERABLE vs REFUSED - the split that matters commercially"
# dev/clean-cases.mjs reports flagged readings at about 79% and that reads like
# a weakness in half the population. Nearly all of them are the reference
# REFUSING to build - over 120", wider than the door, wire past the ID's limit -
# and those doors cannot be bought at any accuracy. The readings it warns about
# and will still build come out at 100%.
if [ -f "$VALIDATION" ]; then
    node dev/orderable.mjs "$VALIDATION" "$VALIDATION2" 2>&1 | sed 's/^/  /'
fi

echo ""
echo "TUNED SAMPLES - knobs were set against these, so they read high"
node dev/clean-cases.mjs dev/eval-rand-seed777001.json dev/eval-soft2-spread.json \
    dev/eval-clean.json 2>&1 | head -2 | sed 's/^/  /'

echo ""
echo "IN SAMPLE - the fitter's own training data, for regressions only"
# One run, reused: dev/replay.mjs walks 8000 readings and is the slow part.
REPLAY=$(node dev/replay.mjs 2>&1 || true)
printf '%s\n' "$REPLAY" | grep -E "byte-identical|verified reading|not asserted" | sed 's/^/  /'
# The invariant total is READ FROM THE SUITE, not written down here. It was
# hardcoded as /16 and silently stopped matching the moment a seventeenth was
# added. Counting FAIL lines instead does not work either - the corpus section
# prints its own, and they outnumber these by a hundred to one.
printf "  invariants: %s/%s\n" \
    "$(printf '%s\n' "$REPLAY" | grep -c '^  PASS')" \
    "$(node --input-type=module -e 'import { INVARIANTS } from "./dev/invariants.mjs"; console.log(INVARIANTS.length);')"

echo ""
echo "SINGLE - external random draws, the reference's own wire fed back"
# ALL THREE DRAWS, because the first one alone was lopsided. eval-single.json
# is 181 clean readings and only SIX of them are hi-lift, on one drum and one
# spring ID - so "Single is 100%" rested on nothing at all for hi-lift, and on
# nothing for the 525-54HL and D800-120 drums, which it never drew. The two
# seeded draws beside it were taken to fill exactly those holes.
SINGLE_SETS=""
for f in dev/eval-single.json \
         dev/eval-single-hilift-seed20261008.json \
         dev/eval-single-tall-seed20261008001.json; do
    [ -f "$f" ] && SINGLE_SETS="$SINGLE_SETS $f"
done

if [ -n "$SINGLE_SETS" ]; then
    # shellcheck disable=SC2086
    node dev/single-external.mjs $SINGLE_SETS | sed 's/^/  /'
    echo ""
    echo "SINGLE BY SLICE - read the n column before the percentages"
    # shellcheck disable=SC2086
    node dev/single-breakdown.mjs $SINGLE_SETS | sed 's/^/  /'
fi

echo ""
echo "REFERENCE WARNINGS - agreement reading by reading"
node dev/warn-check.mjs dev/pulled-0*.json dev/pulled-k*.json dev/pulled-a1.json 2>&1 | sed 's/^/  /'
