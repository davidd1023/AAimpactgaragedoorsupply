#!/bin/sh
# Refit and install the past-120" offsets, in the ONE order that is correct.
#
#   sh dev/apply-over120.sh
#
# EMPTY, DERIVE, INSTALL. The deriver reads the engine's own output, which
# already carries whatever offsets are installed - so fitting without clearing
# them first fits a correction on top of itself and reports that none is
# needed. That happened once; see the header of dev/derive-over120.mjs.
set -e
cd "$(dirname "$0")/.."
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("static/src/js/spring_engineering.js")
s = p.read_text()
m = re.search(r"const DUPLEX_LONG_OFFSET = \{.*?\n\};", s, re.S)
assert m, "DUPLEX_LONG_OFFSET not found"
p.write_text(s[:m.start()] + "const DUPLEX_LONG_OFFSET = {\n};" + s[m.end():])
print("cleared the installed table")
PY
node dev/derive-over120.mjs
python3 - <<'PY'
import pathlib, re, json
offs = json.loads(pathlib.Path("dev/over120-offsets.json").read_text())
tbl = "\n".join(
    '    "{}": {{ t: {}, lo: {}, hi: {} }},'.format(
        k, "null" if v["t"] is None else v["t"], v["lo"], v["hi"])
    for k, v in sorted(offs.items()))
p = pathlib.Path("static/src/js/spring_engineering.js")
s = p.read_text()
m = re.search(r"const DUPLEX_LONG_OFFSET = \{.*?\n\};", s, re.S)
p.write_text(s[:m.start()] + "const DUPLEX_LONG_OFFSET = {\n" + tbl + "\n};" + s[m.end():])
print(f"installed {len(offs)} rungs")
PY
