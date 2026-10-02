#!/bin/sh
# Re-derive the calibration table from every reading and install it.
#
#   sh dev/apply.sh
#
# Kept as a script because the loop is now routine: pull a batch, run this,
# look at the score. The table is never hand-edited.
set -e
cd "$(dirname "$0")/.."
node dev/derive.mjs --json > /tmp/derived.json
python3 - <<'PY'
import json
rows=json.load(open('/tmp/derived.json'))
lines=[]
for r in rows:
    if r['K'] is None: continue
    e=""
    if r['byCount']:
        bandparts=[]; lineparts=[]
        for sp,v in sorted(r['byCount'].items(), key=lambda kv:int(kv[0])):
            if 'line' in v:
                L=v['line']
                if 'mid' in L:
                    lineparts.append("%s: { a: %g, b: %g, a2: %g, lo: %g, mid: %g, hi: %g }"
                                     %(sp,L['a'],L['b'],L['a2'],L['lo'],L['mid'],L['hi']))
                else:
                    lineparts.append("%s: { a: %g, b: %g, lo: %g, hi: %g }"%(sp,L['a'],L['b'],L['lo'],L['hi']))
            else:
                bs=", ".join("{ upTo: %g, bonus: %g }"%(b['upTo'],b['bonus']) for b in v['bands'])
                bandparts.append("%s: [%s]"%(sp,bs))
        if bandparts: e+=", byCount: { "+", ".join(bandparts)+" }"
        if lineparts: e+=", lineByCount: { "+", ".join(lineparts)+" }"
    if abs(r['outer']-0.2625)<1e-9 and abs(r['inner']-0.2253)<1e-9:
        e+=", long: { from: 25.5, byCount: { 2: 0.620, 3: 0.050 }, above: 2.25 }"
    lines.append("            { outerWire: %g, innerWire: %g, K: %.1f, n: %d%s },"
                 %(r['outer'],r['inner'],r['K'],r['n'],e))
p='static/src/js/spring_engineering.js'
s=open(p).read()
a=s.index("        calibration: ["); b=s.index("        ],",a)
open(p,'w').write(s[:a]+"        calibration: [\n"+"\n".join(lines)+"\n"+s[b:])
print("installed %d rungs"%len(lines))
PY
