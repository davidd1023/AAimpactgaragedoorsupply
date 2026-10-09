#!/bin/sh
# The rung-volume pull campaign: generate, pull, import, one batch at a time.
#
#   sh dev/rung-campaign.sh [first] [last]      default 6 14
#
# WHY A SCRIPT IN THE REPO. It lived in a scratchpad and the scratchpad was
# cleared mid-campaign, taking the runner and every log with it. The readings
# survived only because each batch is imported into dev/corpus.json before the
# next one starts - which is also why being killed costs at most one batch.
#
# WHAT IT IS FOR. dev/rung-volume.sh shows per-rung LENGTH volume causes length
# accuracy: starving a rung to 160 readings costs it about 7 points and the
# curve is still climbing at 320. Only four of fifty rungs were above 300. This
# brings the rest up, aiming with dev/rung-target-sample.mjs.
#
# A LOCK, because two instances once ran at once. The first was launched with
# nohup from a shell that was then reaped; it looked dead - no log file - so a
# second was started. Both were alive, both pulled the SAME sweep into the SAME
# file, and 800 requests against someone else's server yielded 110 usable
# readings. One instance, enforced.
LOCK=${TMPDIR:-/tmp}/spring-rung-campaign.lock

if ! mkdir "$LOCK" 2>/dev/null; then
    echo "another campaign instance holds $LOCK - refusing to start" >&2
    exit 1
fi

trap 'rmdir "$LOCK" 2>/dev/null' EXIT INT TERM

cd "$(dirname "$0")/.."
FIRST=${1:-6}
LAST=${2:-14}
LOGS=$(mktemp -d)
echo "logs in $LOGS"

I=$FIRST

while [ "$I" -le "$LAST" ]; do
    SW=dev/sweeps-V$I.json
    PU=dev/pulled-V$I.json

    # APPLY BEFORE GENERATING. The generator reads each rung's current count
    # from the INSTALLED table, so a stale table misallocates the batch. Batch
    # V3 was generated before the previous batch had been applied and spent 75
    # of its 400 requests on a rung that was already full.
    sh dev/apply.sh > "$LOGS/apply-pre-V$I.log" 2>&1

    if [ -f "$SW" ]; then
        echo "V$I: $SW exists, reusing it"
    else
        echo "=== V$I generating ==="
        node dev/rung-target-sample.mjs "$SW" "2026100810$I" 400 30000 \
            > "$LOGS/gen-V$I.log" 2>&1
    fi

    N=$(python3 -c "import json;print(len(json.load(open('$SW'))))" 2>/dev/null || echo 0)
    echo "V$I: $N cases"

    if [ "$N" -lt 10 ]; then
        echo "nothing material left to need - stopping at V$I"
        break
    fi

    echo "=== V$I pulling $N ==="
    node dev/pull.mjs "$SW" "$PU" > "$LOGS/V$I.log" 2>&1
    OK=$(python3 -c "import json;d=json.load(open('$PU'));print(sum(1 for r in d if r.get('status')=='success'))" 2>/dev/null || echo 0)
    echo "V$I: pulled, $OK clean"

    node dev/import.mjs "$PU" "V$I" "Rung-targeted volume batch $I" \
        > "$LOGS/imp-V$I.log" 2>&1
    echo "V$I: imported"
    I=$((I + 1))
done

sh dev/apply.sh > "$LOGS/apply-final.log" 2>&1
echo "CAMPAIGN DONE (V$FIRST..V$((I - 1)))"
