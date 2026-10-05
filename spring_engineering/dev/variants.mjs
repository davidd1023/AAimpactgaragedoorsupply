// Try many length models at once. Each is fitted on the TRAINING pulls and
// scored on CLEAN external readings - the doors the reference answers without
// a message, which are the ones that get ordered.
//
//   node dev/variants.mjs
//
// Everything is computed from the reference's own reported TIPPT and wire, so
// this scans models without going through the app. The winner gets built.
import { readFileSync, readdirSync } from "node:fs";

const HERE = "/home/odoo/src/user/spring_engineering/dev";
const TC = 10.2;
const div = (w, id) => (30000000 * Math.pow(w, 5)) / (TC * (id + w));
const EVAL = /^(eval|biased)/;

function load(pred, cleanOnly) {
    const out = [];

    for (const f of readdirSync(HERE)) {
        if (!/\.json$/.test(f) || f === "corpus.json" || !pred(f)) continue;

        let d;

        try { d = JSON.parse(readFileSync(`${HERE}/${f}`, "utf8")); } catch { continue; }

        for (const r of d) {
            if (r.error || !r.data || !r.data.innerSpring) continue;
            if (!r.data.totalInchPoundPerTurn) continue;

            const i = r.input;

            if ((i.assembly ?? "Duplex") !== "Duplex") continue;
            if (Number(i.innerId) !== 3.75) continue;

            const L = r.data.innerSpring.springLength;

            if (!(L > 0) || L > 120) continue;

            const msgs = (r.messages ?? []).filter((m) => !/contact us/i.test(m));

            if (cleanOnly && (msgs.length || r.status !== "success")) continue;

            const iw = r.data.innerSpring.wireSize;
            const ow = r.data.outerSpring.wireSize;

            out.push({
                rung: `${ow}/${iw}`, sp: i.springs, L, clean: !msgs.length,
                ratio: ow / iw,
                raw: i.springs * (div(iw, 3.75) + div(ow, 6)) /
                     (Math.round(r.data.totalInchPoundPerTurn * 10) / 10),
            });
        }
    }

    return out;
}

const train = load((f) => !EVAL.test(f), false);
const test = load((f) => /^eval-/.test(f), true);

// --- the grid --------------------------------------------------------------
const snap = (x, off) => Math.round(x - off) + off;
const grid = (x, sp, off2) =>
    sp === 1 ? Math.round(x)
        : sp >= 3 ? snap(x, 0.25)
            : snap(x, off2 ?? 0);

// --- variants --------------------------------------------------------------
// Each returns a model: fit(trainingRows) -> predict(row) -> length
const VARIANTS = {
    "A  sMult per rung": {
        key: (r) => r.rung,
        fit(g) {
            let best = null;

            for (const off2 of [0, 0.25]) {
                for (let b = -320; b <= 320; b++) {
                    const m = 1 + b / 4000;
                    let ok = 0;

                    for (const r of g) {
                        if (Math.abs(grid(r.raw * m, r.sp, off2) - r.L) < 1e-9) ok++;
                    }

                    if (!best || ok > best.ok) best = { ok, m, off2 };
                }
            }

            return best;
        },
        predict: (p, r) => grid(r.raw * p.m, r.sp, p.off2),
    },
    "B  sMult per rung+count": {
        key: (r) => `${r.rung}|${r.sp}`,
        fit(g) {
            let best = null;

            for (const off2 of [0, 0.25]) {
                for (let b = -320; b <= 320; b++) {
                    const m = 1 + b / 4000;
                    let ok = 0;

                    for (const r of g) {
                        if (Math.abs(grid(r.raw * m, r.sp, off2) - r.L) < 1e-9) ok++;
                    }

                    if (!best || ok > best.ok) best = { ok, m, off2 };
                }
            }

            return best;
        },
        predict: (p, r) => grid(r.raw * p.m, r.sp, p.off2),
    },
    "C  sMult + integer shift": {
        key: (r) => r.rung,
        fit(g) {
            let best = null;

            for (const off2 of [0, 0.25]) {
                for (const k of [-1, 0, 1]) {
                    for (let b = -320; b <= 320; b++) {
                        const m = 1 + b / 4000;
                        let ok = 0;

                        for (const r of g) {
                            if (Math.abs(grid(r.raw * m, r.sp, off2) + k - r.L) < 1e-9) ok++;
                        }

                        if (!best || ok > best.ok) best = { ok, m, off2, k };
                    }
                }
            }

            return best;
        },
        predict: (p, r) => grid(r.raw * p.m, r.sp, p.off2) + p.k,
    },
    "D  sMult + additive inches": {
        key: (r) => r.rung,
        fit(g) {
            let best = null;

            for (const off2 of [0, 0.25]) {
                for (let a = -12; a <= 12; a++) {
                    const add = a / 8;

                    for (let b = -200; b <= 200; b += 2) {
                        const m = 1 + b / 4000;
                        let ok = 0;

                        for (const r of g) {
                            if (Math.abs(grid(r.raw * m + add, r.sp, off2) - r.L) < 1e-9) ok++;
                        }

                        if (!best || ok > best.ok) best = { ok, m, off2, add };
                    }
                }
            }

            return best;
        },
        predict: (p, r) => grid(r.raw * p.m + p.add, r.sp, p.off2),
    },
    "E  per-count offset too": {
        key: (r) => r.rung,
        fit(g) {
            let best = null;
            const offs = [0, 0.25];

            for (const o1 of offs) {
                for (const o2 of offs) {
                    for (let b = -320; b <= 320; b += 2) {
                        const m = 1 + b / 4000;
                        let ok = 0;

                        for (const r of g) {
                            const off = r.sp === 1 ? o1 : r.sp >= 3 ? 0.25 : o2;
                            if (Math.abs(snap(r.raw * m, off) - r.L) < 1e-9) ok++;
                        }

                        if (!best || ok > best.ok) best = { ok, m, o1, o2 };
                    }
                }
            }

            return best;
        },
        predict: (p, r) => snap(r.raw * p.m,
            r.sp === 1 ? p.o1 : r.sp >= 3 ? 0.25 : p.o2),
    },
    "F  global sMult(wire ratio)": {
        key: () => "*",
        fit(g) {
            // one line for every rung: sMult = a + b * (outer/inner)
            let best = null;

            for (let bi = -1200; bi <= 0; bi += 4) {
                const b = bi / 1000;

                for (let ai = 1000; ai <= 2600; ai += 4) {
                    const a = ai / 1000;
                    let ok = 0;

                    for (const r of g) {
                        const m = a + b * r.ratio;
                        if (Math.abs(grid(r.raw * m, r.sp, r.sp === 2 ? 0 : 0) - r.L) < 1e-9) ok++;
                    }

                    if (!best || ok > best.ok) best = { ok, a, b };
                }
            }

            return best;
        },
        predict: (p, r) => grid(r.raw * (p.a + p.b * r.ratio), r.sp, 0),
    },
    "G  per rung, formula fallback": {
        key: (r) => r.rung,
        fit(g) {
            let best = null;

            for (const off2 of [0, 0.25]) {
                for (let b = -320; b <= 320; b++) {
                    const m = 1 + b / 4000;
                    let ok = 0;

                    for (const r of g) {
                        if (Math.abs(grid(r.raw * m, r.sp, off2) - r.L) < 1e-9) ok++;
                    }

                    if (!best || ok > best.ok) best = { ok, m, off2 };
                }
            }

            return best;
        },
        // the fallback is supplied by the harness below
        predict: (p, r) => grid(r.raw * p.m, r.sp, p.off2),
        fallback: (r) => grid(r.raw * (1.6978 - 0.5580 * r.ratio), r.sp, 0),
    },
    "H  fitted on CLEAN only": {
        key: (r) => r.rung,
        cleanOnly: true,
        fit(g) {
            let best = null;

            for (const off2 of [0, 0.25]) {
                for (let b = -320; b <= 320; b++) {
                    const m = 1 + b / 4000;
                    let ok = 0;

                    for (const r of g) {
                        if (Math.abs(grid(r.raw * m, r.sp, off2) - r.L) < 1e-9) ok++;
                    }

                    if (!best || ok > best.ok) best = { ok, m, off2 };
                }
            }

            return best;
        },
        predict: (p, r) => grid(r.raw * p.m, r.sp, p.off2),
    },
};

console.log(`${train.length} training readings, ${test.length} clean external readings\n`);
console.log("variant                       in sample      CLEAN external");

for (const [name, v] of Object.entries(VARIANTS)) {
    const by = new Map();

    const source = v.cleanOnly ? train.filter((r) => r.clean) : train;

    for (const r of source) {
        const k = v.key(r);
        (by.get(k) ?? by.set(k, []).get(k)).push(r);
    }

    const model = new Map();

    for (const [k, g] of by) {
        if (g.length >= 8) model.set(k, v.fit(g));
    }

    const score = (set) => {
        let n = 0, ok = 0;

        for (const r of set) {
            const p = model.get(v.key(r));
            n++;

            const got = p ? v.predict(p, r)
                : (v.fallback ? v.fallback(r) : null);

            if (got !== null && Math.abs(got - r.L) < 1e-9) ok++;
        }

        return `${ok}/${n} = ${(ok / n * 100).toFixed(1)}%`;
    };

    console.log(`  ${name.padEnd(28)} ${score(train).padEnd(16)} ${score(test)}`);
}
