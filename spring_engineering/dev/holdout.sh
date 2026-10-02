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
    python3 - <<'PY'
import json
rows=json.load(open('/tmp/hd.json'))
lines=[]
for r in rows:
    if r['K'] is None: continue
    e=""
    if r['byCount']:
        bp=[];lp=[]
        for sp,v in sorted(r['byCount'].items(), key=lambda kv:int(kv[0])):
            if 'line' in v:
                L=v['line']; lp.append("%s: { a: %g, b: %g, lo: %g, hi: %g }"%(sp,L['a'],L['b'],L['lo'],L['hi']))
            else:
                bs=", ".join("{ upTo: %g, bonus: %g }"%(b['upTo'],b['bonus']) for b in v['bands'])
                bp.append("%s: [%s]"%(sp,bs))
        if bp: e+=", byCount: { "+", ".join(bp)+" }"
        if lp: e+=", lineByCount: { "+", ".join(lp)+" }"
    if abs(r['outer']-0.2625)<1e-9 and abs(r['inner']-0.2253)<1e-9:
        e+=", long: { from: 25.5, byCount: { 2: 0.620, 3: 0.050 }, above: 2.25 }"
    lines.append("            { outerWire: %g, innerWire: %g, K: %.1f, n: %d%s },"%(r['outer'],r['inner'],r['K'],r['n'],e))
p='static/src/js/spring_engineering.js'
s=open(p).read()
a=s.index("        calibration: ["); b=s.index("        ],",a)
open(p,'w').write(s[:a]+"        calibration: [\n"+"\n".join(lines)+"\n"+s[b:])
PY
    HOLDOUT_MOD=5 HOLDOUT_REM=$k node dev/derive.mjs --json 2>&1 >/dev/null \
        | node dev/holdout-score.mjs
done
