#!/bin/sh
# PARTIAL POOLING OF THE THRESHOLD, measured properly.
#
#   sh dev/shrink-sweep.sh 0 10 25 60   > /home/odoo/logs/shrink.log 2>&1
#
# Each argument is a SHRINK value: a line is pulled toward its rung's
# n-weighted mean by lambda = k / (k + n), so 0 is the shipped fit exactly and
# larger k pools harder. Every value gets the same five folds over the whole
# corpus, and EVERY READING'S OUTCOME IS RECORDED, not just the fold totals.
#
# WHY PER-READING. The 2026-11-12 knob sweep compared fold totals, whose
# standard deviation is 10.5 readings - so it could not resolve anything under
# about +-21 and reported noise as a finding. Pairing the same reading across
# two configurations removes the between-fold variance entirely: only readings
# that CHANGED carry signal, and McNemar's test on those is exact. Read
# dev/shrink-report.mjs for the comparison.
#
# IT INSTALLS A THROWAWAY TABLE INTO THE ENGINE ON EVERY FOLD. The trap puts
# the real one back, but NEVER COMMIT WHILE THIS IS RUNNING - that would ship a
# four-fifths-of-the-corpus table as the product. `git status` first.
set -e
cd "$(dirname "$0")/.."
cp static/src/js/spring_engineering.js /tmp/shrink-backup.js
trap 'cp /tmp/shrink-backup.js static/src/js/spring_engineering.js' EXIT

OUT=${OUT:-/home/odoo/logs/shrink}
# MOD=4 re-runs the whole comparison under a DIFFERENT fold partition, which
# is how the k=60 result was confirmed not to be an artefact of one split.
mkdir -p "$(dirname "$OUT")"

for k in "$@"; do
    : > "$OUT-$k.rows"
    for fold in $(seq 0 $(( ${MOD:-5} - 1 ))); do
        SHRINK=$k HOLDOUT_MOD=${MOD:-5} HOLDOUT_REM=$fold \
            node dev/derive.mjs --json 2>/dev/null > /tmp/shrink-fit.json
        python3 dev/install.py < /tmp/shrink-fit.json
        SHRINK=$k HOLDOUT_MOD=${MOD:-5} HOLDOUT_REM=$fold \
            node dev/derive.mjs --json 2>&1 >/dev/null \
            | PER_READING=1 node dev/holdout-score.mjs >> "$OUT-$k.rows"
        echo "SHRINK=$k fold $fold done"
    done
    echo "SHRINK=$k total: $(grep -c '^ROW' "$OUT-$k.rows") readings, \
$(awk -F'\t' '$1=="ROW"{s+=$3}END{print s}' "$OUT-$k.rows") correct"
done
