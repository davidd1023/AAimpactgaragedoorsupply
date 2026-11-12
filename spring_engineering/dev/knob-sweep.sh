#!/bin/sh
# SWEEP THE FITTER'S OWN GATES, WHICH NOBODY HAD EVER MEASURED.
#
#   sh dev/knob-sweep.sh screen        six configs on fold 0
#   sh dev/knob-sweep.sh confirm 0.10  LINE_SLACK=<v> vs installed, folds 1-4
#
# Only LINE_LEVELS was ever swept (twice, both losses). These three gate the
# fit itself and were left at whatever they were first set to:
#
#   SPLIT_MIN_SIDE  readings needed either side of a floor split   (8)
#   LEVEL_SUPPORT   share of a group a bonus level must carry      (0.06)
#   LINE_SLACK      misses a line fit may tolerate                 (0.18)
#
# WHY IT WAS WORTH ASKING. Pointing dev/over120-levels.mjs at the IN-ENVELOPE
# band shows the two biggest failing groups are TWO-level with 500+ readings:
#
#   0.2625/0.2253 4spr   558 readings  13 fails   levels 0.25:405  1.25:153
#   0.2625/0.2253 3spr   473 readings   7 fails   levels 0.25:347  1.25:126
#
# The form allows two levels, so those failures are neither capacity nor data.
# 53 of the 128 in-envelope failures sit in groups of that shape.
#
# RESULTS SO FAR (2026-11-12), fold 0, 2,587 held-out readings:
#
#   baseline            2413     SPLIT_MIN_SIDE=4   2413   <- no effect
#   LEVEL_SUPPORT=0.03  2417     SPLIT_MIN_SIDE=16  2413   <- no effect either way
#   LEVEL_SUPPORT=0.12  2405     LINE_SLACK=0.10    2423   <- best, +10
#                                LINE_SLACK=0.26    2414
#
# THEN FOLD 1 SAID -1. Fold 0 is the fold the config was CHOSEN on, so it does
# not count - the same mistake as the "+3 readings at cut 0.55" result past
# 120". Folds 2-4 are unrun. INCONCLUSIVE, leaning negative.
#
# EVERY FOLD INSTALLS A THROWAWAY TABLE into the engine file. The trap restores
# it, but never commit while this is running.
set -e
cd "$(dirname "$0")/.."
cp static/src/js/spring_engineering.js /tmp/knob-backup.js
trap 'cp /tmp/knob-backup.js static/src/js/spring_engineering.js' EXIT

score() {   # score <label> <fold> <env assignments...>
    label="$1"; fold="$2"; shift 2
    env "$@" HOLDOUT_MOD=5 HOLDOUT_REM="$fold" \
        node dev/derive.mjs --json 2>/dev/null > /tmp/knob.json
    python3 dev/install.py < /tmp/knob.json >/dev/null
    printf '%-34s' "$label"
    env "$@" HOLDOUT_MOD=5 HOLDOUT_REM="$fold" \
        node dev/derive.mjs --json 2>&1 >/dev/null | node dev/holdout-score.mjs
}

case "${1:-screen}" in
screen)
    echo "ONE FOLD (k=0), out of sample. Baseline first."
    score "baseline (installed defaults)" 0 DUMMY=1
    score "SPLIT_MIN_SIDE=4"   0 SPLIT_MIN_SIDE=4
    score "SPLIT_MIN_SIDE=16"  0 SPLIT_MIN_SIDE=16
    score "LEVEL_SUPPORT=0.03" 0 LEVEL_SUPPORT=0.03
    score "LEVEL_SUPPORT=0.12" 0 LEVEL_SUPPORT=0.12
    score "LINE_SLACK=0.10"    0 LINE_SLACK=0.10
    score "LINE_SLACK=0.26"    0 LINE_SLACK=0.26
    echo "A knob only matters if it beats the baseline by more than fold noise,"
    echo "and fold 0 cannot show that - it is the fold the winner was picked on."
    ;;
confirm)
    v="${2:?usage: sh dev/knob-sweep.sh confirm <LINE_SLACK value>}"
    echo "FOLDS 1-4, never looked at.  installed 0.18 vs $v"
    for k in 1 2 3 4; do
        score "fold $k  installed"      "$k" LINE_SLACK=0.18
        score "fold $k  LINE_SLACK=$v"  "$k" LINE_SLACK="$v"
    done
    echo "It must win on MOST of the four, not on the one it was chosen on."
    ;;
*) echo "usage: sh dev/knob-sweep.sh [screen|confirm <value>]"; exit 1 ;;
esac
