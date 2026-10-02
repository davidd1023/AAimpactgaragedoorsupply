// Laws the Duplex model must obey REGARDLESS of any reference reading.
//
// These are not opinions about the manufacturer's calculator - they are
// statements the code's own comments already make, now enforced. They catch
// the whole class of bug where a continuous rounding wobble flips a discrete
// wire choice and moves the answer by inches.
import { make } from "./harness.mjs";
import { DUPLEX_IDS, TARGETS } from "./cases.mjs";

const DRUM = "CANIMEX/TF D400-144";

// '3 3/4"' -> 3.75. Mirrors the component's own springIdNumber, which is not
// reachable from here because it reads this.state.
function parseId(text) {
    const value = text.replace('"', "").trim();

    if (!value.includes(" ")) {
        return Number(value);
    }

    const [whole, fraction] = value.split(" ");
    const [numerator, denominator] = fraction.split("/");

    return Number(whole) + Number(numerator) / Number(denominator);
}

function duplex(mod, o) {
    return make(mod, {
        assembly: "Duplex", drum: DRUM, springId: '3 3/4" inside 6"',
        weight: "500", doorHeightFeet: 7, ...o,
    });
}

function wireOf(c) {
    const s = c.duplexStep;

    return s ? `${s.outerWire}/${s.innerWire}` : null;
}

// Peak torque at full wind is weight x drum radius; door height does not
// enter it. The comment on DRUMS says exactly this ("the CYCLE COUNT,
// unchanged"), and the comment on DUPLEX_CATALOGUE re-derives it. So the
// SELECTED wire must not depend on door height.
function heightIndependence(mod) {
    const fails = [];

    for (const cycles of TARGETS) {
        for (let w = 250; w <= 900; w += 2) {
            const seen = new Map();

            for (let h = 7; h <= 14; h += 0.5) {
                const wire = wireOf(duplex(mod, { weight: String(w), doorHeightFeet: h, cycles }));

                if (wire && !seen.has(wire)) {
                    seen.set(wire, h);
                }
            }

            if (seen.size > 1) {
                fails.push(
                    `${w} lb, target ${cycles}: height changes the wire -> ` +
                    [...seen].map(([k, h]) => `${k} @${h}ft`).join(", ")
                );
            }
        }
    }

    return fails;
}

// Track radius moves turns and the multiplier in opposite directions, leaving
// their product - and therefore torque - unchanged. The RADIUS_TURN_DROP
// comment states it outright ("the cycle count never moved"). So radius must
// not change the wire either.
function radiusIndependence(mod) {
    const fails = [];

    for (const cycles of TARGETS) {
        for (let w = 250; w <= 900; w += 4) {
            for (const springs of [1, 2, 3, 4]) {
                const seen = new Map();

                for (const radius of ["15", "12", "LHR"]) {
                    const wire = wireOf(duplex(mod, { weight: String(w), springs, radius, cycles, doorHeightFeet: 9 }));

                    if (wire && !seen.has(wire)) {
                        seen.set(wire, radius);
                    }
                }

                if (seen.size > 1) {
                    fails.push(
                        `${w} lb, ${springs} spring(s), target ${cycles}: radius changes the wire -> ` +
                        [...seen].map(([k, r]) => `${k} @r${r}`).join(", ")
                    );
                }
            }
        }
    }

    return fails;
}

// A heavier door can never need a SOFTER pair. Stiffness is the ordering the
// candidate ladder is built on, so this is monotonicity of the selection.
function weightMonotonic(mod) {
    const fails = [];

    for (const cycles of TARGETS) {
        for (const springs of [1, 2, 4]) {
            let prev = null;

            for (let w = 200; w <= 1000; w += 2) {
                const c = duplex(mod, { weight: String(w), springs, cycles, doorHeightFeet: 9 });
                const step = c.duplexStep;

                if (!step) {
                    continue;
                }

                if (prev && step.S < prev.S - 1e-6) {
                    fails.push(
                        `target ${cycles}, ${springs} spring(s): ${w} lb picks S=${step.S.toFixed(0)} ` +
                        `(${step.outerWire}/${step.innerWire}) but ${w - 2} lb picked the STIFFER ` +
                        `S=${prev.S.toFixed(0)} (${prev.outerWire}/${prev.innerWire})`
                    );
                }

                prev = step;
            }
        }
    }

    return fails;
}

// The chosen pair must reach the ACCEPTANCE FRACTION of the target, and must
// be the softest pair that does.
//
// This invariant used to demand the target outright, and it failed the moment
// DUPLEX_ACCEPT_FRACTION was introduced - correctly, because it encoded an
// assumption the reference does not share. Two measured rejection boundaries
// show it accepting 9,000 cycles against a 10,000 target and only stepping up
// when the rung would fall below that, so the contract is the fraction, not
// the target. See DUPLEX_ACCEPT_FRACTION.
//
// The "softest that qualifies" half matters independently: cycle life is not
// monotonic along the ladder, so the first qualifying rung in ladder order is
// not necessarily the softest qualifying one.
function targetMet(mod) {
    const fails = [];

    for (const cycles of TARGETS) {
        for (let w = 250; w <= 900; w += 4) {
            const c = duplex(mod, { weight: String(w), cycles, doorHeightFeet: 10 });
            const step = c.duplexStep;

            if (!step) {
                continue;
            }

            const reach = c.cycleTarget * mod.DUPLEX_ACCEPT_FRACTION;
            const qualifying = c.duplexCandidates.filter(
                (s) => c.duplexCyclesForStep(s, { rounded: false }) >= reach
            );

            if (!qualifying.length) {
                continue;
            }

            const got = c.duplexCyclesForStep(step, { rounded: false });

            if (got < reach) {
                fails.push(
                    `${w} lb, target ${cycles}: chose ${step.outerWire}/${step.innerWire} ` +
                    `at ${Math.round(got)} cycles, under the ${Math.round(reach)} floor, ` +
                    `while ${qualifying.length} rung(s) qualify`
                );
                continue;
            }

            const softest = qualifying.reduce((a, b) => (b.S < a.S ? b : a));

            if (softest.S < step.S - 1e-6) {
                fails.push(
                    `${w} lb, target ${cycles}: chose ${step.outerWire}/${step.innerWire} ` +
                    `(S=${step.S.toFixed(0)}) but ${softest.outerWire}/${softest.innerWire} ` +
                    `(S=${softest.S.toFixed(0)}) also qualifies and is softer`
                );
            }
        }
    }

    return fails;
}

// No pair may be offered that cannot physically be built: the inner spring
// has to fit inside the outer, C and K have to be positive, and the reported
// lengths have to be finite and positive.
function physicallyValid(mod) {
    const fails = [];

    for (const springId of DUPLEX_IDS) {
        for (const cycles of TARGETS) {
            for (const weight of ["200", "500", "900"]) {
                const c = duplex(mod, { springId, cycles, weight, doorHeightFeet: 9 });
                const pair = c.duplexPair;

                if (!pair) {
                    continue;
                }

                for (const s of c.duplexCandidates) {
                    const tag = `${springId} ${s.outerWire}/${s.innerWire}`;

                    // C is gone - the length now comes from the catalog
                    // formula, which has no fitted constant. K is all that
                    // remains and it must be positive to give a real body.
                    if (!(s.K > 0)) {
                        fails.push(`${tag}: nonphysical K=${s.K}`);
                    }

                    if (pair.innerId + 2 * s.innerWire >= pair.outerId) {
                        fails.push(`${tag}: inner spring does not fit inside the outer`);
                    }
                }

                const inner = c.duplexInnerLength;
                const outer = c.duplexOuterLength;

                if (!(inner > 0) || !Number.isFinite(inner)) {
                    fails.push(`${springId} ${weight} lb target ${cycles}: inner length ${inner}`);
                }

                if (!(outer > inner)) {
                    fails.push(`${springId} ${weight} lb target ${cycles}: outer ${outer} not longer than inner ${inner}`);
                }
            }
        }
    }

    return fails;
}

// A stiffer wire must never be offered than the spring ID can be wound with.
// WIRE_LIMITS carries the band; the Duplex pairs currently borrow nothing, so
// this reports rather than asserts until the bands are known.
function wireBand(mod) {
    const fails = [];
    const bands = mod.WIRE_LIMITS;

    for (const springId of DUPLEX_IDS) {
        const c = duplex(mod, { springId, cycles: "10,000", weight: "900" });
        const pair = c.duplexPair;

        if (!pair) {
            continue;
        }

        const innerKey = Object.keys(bands).find(
            (k) => Math.abs(parseId(k) - pair.innerId) < 1e-9
        );

        if (!innerKey) {
            continue;
        }

        const band = bands[innerKey];

        for (const s of c.duplexCandidates) {
            // MEASURED RUNGS ARE EXEMPT, and this invariant used to assert
            // the opposite. The published band is a SINGLE-spring band; the
            // reference winds 0.4218, 0.4305 and 0.4615 inner wires on the
            // 3 3/4" inner spring, all with readings to prove it. Asserting
            // the Single band over a measured Duplex rung is asserting that
            // real readings are impossible, and it is what kept the stiff end
            // of the ladder out of the candidate list.
            //
            // What is still worth pinning: a GENERATED rung is pure
            // extrapolation, and it must stay inside sizes that have been
            // seen used.
            if (s.measured) {
                continue;
            }

            if (s.innerWire > band.max + 1e-9 || s.innerWire < band.min - 1e-9) {
                fails.push(
                    `${springId}: offers inner wire ${s.innerWire}" outside the ` +
                    `${band.minText}-${band.maxText} band for ${innerKey}`
                );
            }
        }
    }

    return fails;
}

// The weight used for the arithmetic may never exceed the drum's rating. The
// reference caps it and recomputes; this is the enforced version of that.
function weightClamped(mod) {
    const fails = [];

    for (const drum of Object.keys(mod.DRUM_LIMITS)) {
        const max = mod.DRUM_LIMITS[drum].maxWeight;

        if (!max) {
            continue;
        }

        for (const weight of [max - 10, max, max + 1, max + 200, max * 2]) {
            const c = duplex(mod, { drum, weight: String(weight) });
            const used = c.duplexEffectiveWeight;

            if (used > max + 1e-9) {
                fails.push(`${drum}: entered ${weight} lb, computed on ${used} lb, over the ${max} lb rating`);
            }

            if (weight <= max && Math.abs(used - weight) > 1e-9) {
                fails.push(`${drum}: entered ${weight} lb, under the ${max} lb rating, but computed on ${used} lb`);
            }
        }
    }

    return fails;
}

// The door height used must never exceed the drum's nameplate height.
//
// The reference FREEZES its answer at maxHeight - on D400-96 at 375 lb the
// multiplier, turns and TIPPT are identical at 96", 108", 120", 132" and 144"
// - so a taller door must compute on the cap, not on what was typed. The
// limit sat in DRUM_LIMITS being used only for a Single warning while the
// Duplex path fed the entered height straight into the multiplier, growing a
// 20.25" spring to 29.25".
//
// Checked through the multiplier rather than the height getter, because the
// height only matters insofar as it moves the answer: past the cap the
// multiplier must stop changing entirely.
function heightClamped(mod) {
    const fails = [];

    for (const drum of Object.keys(mod.DRUM_LIMITS)) {
        const max = mod.DRUM_LIMITS[drum].maxHeight;

        if (!max) {
            continue;
        }

        const at = (inches) => duplex(mod, {
            drum,
            weight: "375",
            doorHeightFeet: Math.floor(inches / 12),
            doorHeightInches: inches % 12,
        });
        const capped = at(max).multiplierExact;

        for (const over of [max + 12, max + 24, max + 48, max * 2]) {
            const m = at(over).multiplierExact;

            if (Math.abs(m - capped) > 1e-12) {
                fails.push(
                    `${drum}: ${over}" gives multiplier ${m}, but the ${max}" cap gives ${capped}` +
                    " - the height is not being clamped"
                );
            }
        }

        // Under the cap it must still track the entered height, or the clamp
        // has been applied where it does not belong.
        const under = at(max - 12).multiplierExact;

        if (Math.abs(under - capped) < 1e-12) {
            fails.push(`${drum}: ${max - 12}" and ${max}" give the same multiplier - over-clamped`);
        }
    }

    return fails;
}

// Duplex must raise no warning that is derived from the Wire Size dropdown.
//
// Duplex picks both wires itself and does not show that control, so anything
// computed from it is stale. Before this was gated, a red "Low Cycle Life"
// fired on 7 of 8 Duplex doors quoting a cycle count unrelated to the result
// on screen.
// The cycles-low caution must stay YELLOW.
//
// The reference's equivalent is red, and ours cannot be: measured against our
// computed cycle count, the readings the reference warns on and the ones it
// passes overlap completely (ratio 0.9646 to 1.0027 on both sides). Every
// threshold either misses all 184 or raises 393 false alarms. Red would assert
// a rejection we cannot actually determine, and 393 red errors on 2,936 doors
// would train the user to ignore the panel.
//
// If someone later makes the cycle count accurate enough to separate the two
// groups, this invariant is the thing to delete - deliberately, with the
// measurement redone.
function cyclesLowStaysCaution(mod) {
    const fails = [];

    for (const drum of Object.keys(mod.DRUM_LIMITS)) {
        for (const weight of [480, 800, 900, 1200]) {
            for (const springs of [1, 2, 3, 4]) {
                const c = duplex(mod, {
                    drum, springs, weight: String(weight), cycles: "10,000",
                });
                const w = (c.warnings || []).find((x) => x.id === "duplex-cycles-low");

                if (w && w.severity !== "yellow") {
                    fails.push(
                        `${drum} ${weight}lb ${springs}spr: cycles-low is ` +
                        `${w.severity}, and it has not earned better than yellow`
                    );
                }
            }
        }
    }

    return fails;
}

function noStaleWireWarnings(mod) {
    const stale = new Set([
        "wire-over-max",
        "wire-under-min",
        "cycles-over-max",
        "cycles-low",
    ]);
    const fails = [];

    for (const springId of DUPLEX_IDS) {
        for (const wireSize of ['0.125"', '0.25"', '0.5"', '0.625"']) {
            for (const weight of ["200", "470", "750"]) {
                for (const springs of [1, 2, 4]) {
                    const c = duplex(mod, { springId, weight, springs, wireSize, showWarnings: true });

                    for (const w of c.warnings || []) {
                        if (stale.has(w.id)) {
                            fails.push(
                                `${springId} ${weight} lb ${springs} spring(s), dropdown at ` +
                                `${wireSize}: raised ${w.id} - "${w.message.slice(0, 60)}"`
                            );
                        }
                    }
                }
            }
        }
    }

    return fails;
}

// Nothing in the Duplex path may depend on the Wire Size dropdown.
//
// This is the general form of two bugs that were found separately: four
// warnings computed from the dropdown, and the assembly length built from the
// Single spring length and the dropdown wire. Duplex picks both its wires, so
// every Duplex output must be invariant to that control.
function duplexIgnoresWireDropdown(mod) {
    const sizes = ['0.125"', '0.2253"', '0.25"', '0.375"', '0.625"'];
    const outputs = [
        "duplexInnerLength",
        "duplexOuterLength",
        "duplexInnerWire",
        "duplexOuterWire",
        "duplexCycles",
        "assemblyLengthExact",
    ];
    const fails = [];

    for (const weight of ["200", "348", "470", "750"]) {
        for (const springs of [1, 2, 3]) {
            const seen = {};

            for (const wireSize of sizes) {
                const c = duplex(mod, { weight, springs, wireSize, showWarnings: true });

                for (const key of outputs) {
                    const value = String(c[key]);

                    if (seen[key] === undefined) {
                        seen[key] = { value, wireSize };
                    } else if (seen[key].value !== value) {
                        fails.push(
                            `${weight} lb ${springs} spring(s): ${key} changed with the ` +
                            `dropdown - ${seen[key].value} at ${seen[key].wireSize}, ` +
                            `${value} at ${wireSize}`
                        );
                    }
                }
            }
        }
    }

    return fails;
}

export const INVARIANTS = [
    { name: "cycle life / wire choice is independent of door height", run: heightIndependence },
    { name: "cycle life / wire choice is independent of track radius", run: radiusIndependence },
    { name: "a heavier door never gets a softer pair", run: weightMonotonic },
    { name: "the chosen pair meets the target when one on the ladder can", run: targetMet },
    { name: "every offered pair is physically buildable", run: physicallyValid },
    { name: "generated inner wire stays inside the spring ID's band", run: wireBand },
    { name: "the weight used never exceeds the drum's rating", run: weightClamped },
    { name: "the door height used never exceeds the drum's nameplate", run: heightClamped },
    { name: "the cycles-low flag stays a caution, not a verdict", run: cyclesLowStaysCaution },
    { name: "Duplex raises no Wire-Size-dropdown warning", run: noStaleWireWarnings },
    { name: "no Duplex output depends on the Wire Size dropdown", run: duplexIgnoresWireDropdown },
];
