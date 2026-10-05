#!/bin/sh
# Five-fold holdout over the WHOLE corpus. Each fold withholds a fifth of the
# distinct readings from the fit, installs that table, and scores only the
# withheld ones - so every reading is scored exactly once, out of sample.
#
# This is the number that matters. The in-sample corpus figure says only that
# the fitter can reproduce what it was shown.
set -e
cd "$(dirname "$0")/.."
cp static/src/js/spring_engineering.js /tmp/holdout-backup.js
trap 'cp /tmp/holdout-backup.js static/src/js/spring_engineering.js' EXIT
for k in 0 1 2 3 4; do
    HOLDOUT_MOD=5 HOLDOUT_REM=$k node dev/derive.mjs --json 2>/dev/null > /tmp/hd.json
    python3 dev/install.py < /tmp/hd.json
    HOLDOUT_MOD=5 HOLDOUT_REM=$k node dev/derive.mjs --json 2>&1 >/dev/null \
        | node dev/holdout-score.mjs
done
