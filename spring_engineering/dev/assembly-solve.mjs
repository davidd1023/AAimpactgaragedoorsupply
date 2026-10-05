// Measure the reference's assembly length, which it never reports.
//
//   node dev/assembly-solve.mjs dev/pulled-a1.json
//
// The reference warns when its assembly exceeds the door width, and the width
// is an input - so sweeping the width one inch at a time brackets the assembly
// length to the inch. Each bracket says
//
//   maxWarn < refAssembly <= minQuiet
//
// and under assembly = springs*(outerLength + turns*wire) + H that is an
// interval for H. Intersecting the intervals over every bracket pins it.
//
// TWO THINGS THIS GETS WRONG IF DONE CARELESSLY, both of which it did:
//
//   A bracket at the EDGE of the swept range is not a bracket, it is the edge.
//   Two such edges implied H = 16.2 against the 28.4 the real brackets agree
//   on, purely because the sweep started above the crossing.
//
//   Solving with OUR length folds our length error into H. One 3-spring case
//   demanded 31.45 until the reference's own 24.25" length was used instead of
//   our 23.25" - a genuine one-inch length miss, not a hardware difference.
import { readFileSync } from "node:fs";

const groups = new Map();

for (const file of process.argv.slice(2)) {
    for (const r of JSON.parse(readFileSync(file, "utf8"))) {
        if (r.error || !r.data || !r.data.outerSpring) {
            continue;
        }

        const i = r.input;
        const key = `${i.springs}|${i.weight}|${i.cycles}|${i.heightInches}|${i.drum}`;
        const warns = (r.messages ?? []).some((m) =>
            /too long for a .* wide door/i.test(m));
        const g = groups.get(key) ?? groups.set(key, { pts: [], d: r.data, i }).get(key);

        g.pts.push({ w: i.widthInches, warns });
    }
}

let lo = -Infinity;
let hi = Infinity;
let used = 0;

console.log("spr  weight  refOuterL  turns   wire     H must lie in");

for (const g of groups.values()) {
    const warn = g.pts.filter((x) => x.warns).map((x) => x.w);
    const quiet = g.pts.filter((x) => !x.warns).map((x) => x.w);

    if (!warn.length || !quiet.length) {
        continue;
    }

    const maxWarn = Math.max(...warn);
    const minQuiet = Math.min(...quiet);
    const lw = Math.min(...g.pts.map((x) => x.w));
    const hw = Math.max(...g.pts.map((x) => x.w));

    // A TIGHT, MONOTONIC bracket and nothing else. Requiring the bracket to
    // be strictly inside the swept range was too strong and threw away every
    // 1-spring measurement: if the lowest width tested warns and the next one
    // up is quiet, the crossing IS between them, and whether even narrower
    // doors also warn is irrelevant. What must hold is that the warning turns
    // off exactly once, and that the two widths either side of it are one
    // inch apart.
    const monotonic =
        g.pts.every((x) => (x.w <= maxWarn ? x.warns : !x.warns));

    if (maxWarn > minQuiet || minQuiet - maxWarn !== 1 || !monotonic) {
        continue;
    }

    void lw;
    void hw;

    const sp = g.i.springs;
    const L = g.d.outerSpring.springLength;
    const wire = g.d.outerSpring.wireSize;
    const turns = g.d.turnsOnSprings;
    const body = sp * (L + turns * wire);
    const a = maxWarn - body;
    const b = minQuiet - body;

    lo = Math.max(lo, a);
    hi = Math.min(hi, b);
    used += 1;

    console.log(
        `  ${sp}  ${String(g.i.weight).padStart(5)}   ${String(L).padStart(7)}  ` +
        `${String(turns).padStart(5)}  ${wire.toFixed(4)}   (${a.toFixed(3)}, ${b.toFixed(3)}]`
    );
}

console.log(
    `\n  ${used} bracket(s)  ->  H in (${lo.toFixed(3)}, ${hi.toFixed(3)}]  ` +
    (lo < hi ? `midpoint ${((lo + hi) / 2).toFixed(3)}` : "CONTRADICTORY")
);
