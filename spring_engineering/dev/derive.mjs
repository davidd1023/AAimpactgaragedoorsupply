// Derive the Duplex calibration table from every reading available.
//
//   node dev/derive.mjs            print the table
//   node dev/derive.mjs --json     machine-readable
//
// WHY. The calibration table used to be hand-maintained, which is how it
// drifted from its own comments in the first place. Every number in it is a
// function of the readings, so it should be COMPUTED from them:
//
//   rungs       every outer/inner pairing the reference has been seen to use
//   K           the cycle model run backwards on each reading, median per rung
//   tLo / tHi   the length thresholds, where readings bracket them
//
// It reads dev/corpus.json plus any dev/pulled*.json, so a new pull improves
// the table by re-running this rather than by editing JavaScript.
import { load, make } from "./harness.mjs";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TC = 10.2;
const COEFF = 124205;
const WEXP = 2.79;
const CEXP = 4.67;
const PAIR = '3 3/4" inside 6"';

const divider = (wire, id) =>
    (30000000 * Math.pow(wire, 5)) / (TC * (id + wire));

const mod = await load();

// --- gather every reading, from pulls and from the hand-entered corpus ------
const readings = [];

for (const f of readdirSync(HERE).filter((f) => /^pulled.*\.json$/.test(f))) {
    for (const r of JSON.parse(readFileSync(join(HERE, f), "utf8"))) {
        if (r.error) {
            continue;
        }

        const i = r.input;
        const d = r.data;

        readings.push({
            state: {
                assembly: "Duplex", drum: i.drum, springId: PAIR,
                springs: i.springs, radius: String(i.radius),
                cycles: Number(i.cycles).toLocaleString("en-US"),
                weight: String(i.weight),
                doorHeightFeet: Math.floor(i.heightInches / 12),
                doorHeightInches: i.heightInches % 12,
            },
            outer: d.outerSpring.wireSize,
            inner: d.innerSpring.wireSize,
            length: d.innerSpring.springLength,
            cycles: d.cycles,
        });
    }
}

for (const r of JSON.parse(readFileSync(join(HERE, "corpus.json"), "utf8")).readings) {
    if (!r.expect || r.expect.duplexInnerLength === undefined) {
        continue;
    }

    if (r.status === "partial" || r.status === "superseded") {
        continue;
    }

    if ((r.state.springId || "").indexOf("3 3/4") !== 0) {
        continue;
    }

    readings.push({
        state: r.state,
        outer: parseFloat(r.expect.duplexOuterWire),
        inner: parseFloat(r.expect.duplexInnerWire),
        length: r.expect.duplexInnerLength,
        cycles: r.referenceCycles,
    });
}

// --- per rung: K from the cycle counts, thresholds from the lengths ---------
const rungs = new Map();

for (const r of readings) {
    const c = make(mod, r.state);
    const springs = Number(r.state.springs) || 2;

    if (!c.tipptExact || !c.turnsExact) {
        continue;
    }

    const key = r.outer + "/" + r.inner;

    if (!rungs.has(key)) {
        rungs.set(key, { outer: r.outer, inner: r.inner, Ks: [], lens: [] });
    }

    const g = rungs.get(key);

    if (r.cycles > 0) {
        const torque = (COEFF * Math.pow(r.inner, WEXP)) / Math.pow(r.cycles, 1 / CEXP);
        const body = divider(r.inner, 3.75) * c.turnsExact / torque;

        g.Ks.push(body * c.tipptExact / (springs / 2));
    }

    const active =
        springs * (divider(r.inner, 3.75) + divider(r.outer, 6)) / c.tipptExact;
    const whole = Math.floor(active);

    g.lens.push({
        springs, active, frac: active - whole,
        bonus: Number((r.length - whole).toFixed(2)),
    });
}

const median = (xs) => {
    const s = xs.slice().sort((a, b) => a - b);

    return s[Math.floor(s.length / 2)];
};

const contradictions = [];

const out = [...rungs.values()]
    .map((g) => {
        const S = 2 * (divider(g.inner, 3.75) + divider(g.outer, 6));
        // thresholds only from 1- and 2-spring readings: 3 and 4 springs sit on
        // a different quarter-inch grid, handled by duplexSnapToGrid
        const low = g.lens.filter((l) => l.springs <= 2);
        const zero = low.filter((l) => l.bonus === 0).map((l) => l.frac);
        const one = low.filter((l) => l.bonus === 1).map((l) => l.frac);
        const quarter = low.filter((l) => l.bonus === 1.25).map((l) => l.frac);
        let tLo = null;
        let tHi = null;

        // only set a threshold where round() is provably wrong: a reading that
        // floors above frac 0.5, or any quarter-inch bonus at all
        if ((zero.length && Math.max(...zero) > 0.5) || quarter.length) {
            const loFloor = zero.length ? Math.max(...zero) : 0;
            const loCeil = quarter.length
                ? Math.min(...quarter)
                : (one.length ? Math.min(...one) : 1);

            // tLo must be STRICTLY above the highest frac seen flooring, or
            // that very reading is misclassified. Where the readings bracket
            // it, take the midpoint; where they only bound it from below, sit
            // just above the bound and assert nothing more.
            tLo = loCeil > loFloor
                ? Number(((loFloor + loCeil) / 2).toFixed(3))
                : Number((loFloor + 0.005).toFixed(3));

            if (quarter.length && one.length) {
                const qMax = Math.max(...quarter);
                const oMin = Math.min(...one);

                tHi = oMin > qMax
                    ? Number(((qMax + oMin) / 2).toFixed(3))
                    : Number((qMax + 0.005).toFixed(3));
            } else {
                tHi = tLo;
            }

            // contradictory readings - the single-threshold model cannot fit
            // this rung, so say so rather than silently choosing
            if (quarter.length && zero.length && Math.min(...quarter) < Math.max(...zero)) {
                contradictions.push(
                    `${g.outer}/${g.inner}: floors at frac ${Math.max(...zero).toFixed(3)} ` +
                    `but adds a quarter at ${Math.min(...quarter).toFixed(3)}`
                );
            }
        }

        return {
            outer: g.outer, inner: g.inner, S,
            K: g.Ks.length ? Number(median(g.Ks).toFixed(1)) : null,
            n: g.Ks.length, nLen: g.lens.length, tLo, tHi,
        };
    })
    .sort((a, b) => a.S - b.S);

if (process.argv.includes("--json")) {
    console.log(JSON.stringify(out, null, 1));
} else {
    console.log(`${readings.length} readings -> ${out.length} rungs\n`);
    console.log("  outer    inner      S        K       K/S     n  nLen   tLo    tHi");

    for (const r of out) {
        console.log(
            "  " + String(r.outer).padEnd(8) + String(r.inner).padEnd(9) +
            r.S.toFixed(0).padStart(6) + String(r.K ?? "-").padStart(10) +
            (r.K ? (r.K / r.S).toFixed(4) : "     -").padStart(9) +
            String(r.n).padStart(4) + String(r.nLen).padStart(5) +
            (r.tLo === null ? "     -      -" :
                r.tLo.toFixed(3).padStart(8) + r.tHi.toFixed(3).padStart(7))
        );
    }

    console.log("\n  n     = readings whose cycle count fed K");
    console.log("  nLen  = readings whose length fed the thresholds");
    console.log("  tLo/tHi blank = no evidence that round() is wrong, so it is left alone");

    if (contradictions.length) {
        console.log("\n  RUNGS WHERE ONE THRESHOLD CANNOT FIT THE READINGS:");

        for (const c of contradictions) {
            console.log("    " + c);
        }
    }
}
