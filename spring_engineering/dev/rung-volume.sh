#!/bin/sh
# Does per-rung LENGTH data volume cause length accuracy? Starve a rung and see.
#
#   sh dev/rung-volume.sh
#
# THE EXPERIMENT. The never-tuned draws show the four rungs with 300+ corpus
# readings at 121/121 and the thinner rungs at 93.9%. That is either causal -
# in which case a rung-targeted pull is worth the rate limit - or it means the
# well-covered rungs are simply the ones a random door lands on, and therefore
# the easy ones. Removing data from a rich rung separates the two for nothing.
#
# It re-derives the table several times and RESTORES it at the end. Run it on a
# clean tree; it checks.
#
# READ THE SEED NOTE. CAP_SEED picks a reproducible RANDOM subsample. Without
# it the cap keeps the first N readings in corpus order, and the corpus is in
# batch order with the early batches deliberately boundary-dense - so
# file-order capping reported 88.43% where a random subsample of the same size
# reports 92.56%. The first run of this experiment used file order and
# overstated the effect by a third. Always quote the seeded numbers.
set -e
cd "$(dirname "$0")/.."

if ! git diff --quiet -- spring_engineering/static/src/js/spring_engineering.js 2>/dev/null; then
    echo "the component has uncommitted changes - commit or stash first, this script rewrites the table" >&2
    exit 1
fi

VAL="dev/eval-validation-seed61006.json dev/eval-validation2-seed20261007.json"
# The four rungs with 300+ length readings.
BIG="0.2625/0.2253,0.273/0.2253,0.3065/0.2437,0.3625/0.283"

restore() {
    sh dev/apply.sh >/dev/null 2>&1
    echo ""
    echo "restored:"
    # shellcheck disable=SC2086
    RUNGS="$BIG" node dev/rung-score.mjs $VAL | sed 's/^/  /'
}
trap restore EXIT

echo "BASELINE - full data, scored on the four rungs with 300+ readings"
# shellcheck disable=SC2086
RUNGS="$BIG" node dev/rung-score.mjs $VAL | sed 's/^/  /'

echo ""
echo "STARVED - the same 121 readings, those four rungs capped (2 seeds each)"

for CAP in 40 80 160 240 320; do
    TOT=0
    for SEED in 11 29; do
        CAP_RUNGS="$BIG" CAP_N="$CAP" CAP_SEED="$SEED" sh dev/apply.sh >/dev/null 2>&1
        # shellcheck disable=SC2086
        V=$(RUNGS="$BIG" node dev/rung-score.mjs $VAL \
            | sed 's/.*exact \([0-9]*\)\/.*/\1/')
        TOT=$((TOT + V))
    done
    echo "  cap $CAP  ->  $(python3 -c "print(f'{$TOT/2/121*100:.2f}%')")"
done
