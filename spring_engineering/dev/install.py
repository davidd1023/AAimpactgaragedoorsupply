# Install a derived calibration (JSON on stdin) into the module source.
#
# ONE COPY, shared by dev/apply.sh and dev/holdout.sh. They each had their own
# and the holdout's went stale the moment a new form was added - it crashed
# with KeyError: 'bands' as soon as regime splits existed, which would have
# looked like the model failing rather than the script being out of date.
import json
import sys

SRC = "static/src/js/spring_engineering.js"


def line_src(line):
    if "mid" in line:
        return ("{ a: %g, b: %g, a2: %g, lo: %g, mid: %g, hi: %g }"
                % (line["a"], line["b"], line["a2"],
                   line["lo"], line["mid"], line["hi"]))
    return ("{ a: %g, b: %g, lo: %g, hi: %g }"
            % (line["a"], line["b"], line["lo"], line["hi"]))


def main():
    rows = json.load(sys.stdin)
    out = []

    for row in rows:
        if row["K"] is None:
            continue

        extra = ""
        bands, lines, splits = [], [], []

        for sp, val in sorted((row["byCount"] or {}).items(),
                              key=lambda kv: int(kv[0])):
            if "split" in val:
                s = val["split"]
                splits.append("%s: { from: %d, below: %s, above: %s }"
                              % (sp, s["from"], line_src(s["below"]),
                                 line_src(s["above"])))
            elif "line" in val:
                lines.append("%s: %s" % (sp, line_src(val["line"])))
            else:
                inner = ", ".join("{ upTo: %g, bonus: %g }" % (b["upTo"], b["bonus"])
                                  for b in val["bands"])
                bands.append("%s: [%s]" % (sp, inner))

        if bands:
            extra += ", byCount: { " + ", ".join(bands) + " }"
        if lines:
            extra += ", lineByCount: { " + ", ".join(lines) + " }"
        if splits:
            extra += ", splitByCount: { " + ", ".join(splits) + " }"

        # The softest rung's long-active-length override is still hand-held.
        if abs(row["outer"] - 0.2625) < 1e-9 and abs(row["inner"] - 0.2253) < 1e-9:
            extra += (", long: { from: 25.5, byCount: { 2: 0.620, 3: 0.050 },"
                      " above: 2.25 }")

        out.append("            { outerWire: %g, innerWire: %g, K: %.1f, n: %d%s },"
                   % (row["outer"], row["inner"], row["K"], row["n"], extra))

    src = open(SRC).read()
    start = src.index("        calibration: [")
    end = src.index("        ],", start)
    open(SRC, "w").write(
        src[:start] + "        calibration: [\n" + "\n".join(out) + "\n" + src[end:]
    )
    print("installed %d rungs" % len(out))


main()
