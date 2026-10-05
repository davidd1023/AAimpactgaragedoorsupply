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
// Each warning's severity must match the one the REFERENCE gives it.
//
// Severity was set by how serious each message sounded, and four were wrong in
// one direction and one in the other. The reference settles it: its JSON
// carries a status per response, so the responses with exactly ONE message
// give that message's own severity. Cone capacity (175 responses), both wire
// bands (155 and 28) and both cycle-life messages (154 and 89) all come back
// "warning"; assembly-too-long (316), spring-length-unsupported and
// height-over-drum (22) come back "error".
//
// Getting this wrong is not cosmetic: red on a pairing the supplier will still
// sell, and amber on a door too tall for the drum, both mislead a quote.
const REFERENCE_SEVERITY = {
    "duplex-mip-over-max": "yellow",
    "duplex-inner-wire-unsold": "yellow",
    "duplex-outer-wire-unsold": "yellow",
    "duplex-cycles-over-max": "yellow",
    "duplex-cycles-low": "yellow",
    "weight-over-max": "yellow",
    "assembly-too-long": "red",
    "duplex-length-unsupported": "red",
    "height-over-max": "red",
};

function severityMatchesReference(mod) {
    const fails = [];
    const seen = new Map();

    for (const drum of Object.keys(mod.DRUM_LIMITS)) {
        for (const springs of [1, 2, 3, 4]) {
            for (const weight of [300, 700, 1200, 1600, 2200]) {
                for (const doorHeightFeet of [7, 9, 14, 20]) {
                    for (const cycles of ["10,000", "300,000"]) {
                        const c = duplex(mod, {
                            drum, springs, weight: String(weight),
                            doorHeightFeet, cycles,
                        });

                        for (const w of c.warnings || []) {
                            if (!seen.has(w.id)) {
                                seen.set(w.id, w.severity);
                            }
                        }
                    }
                }
            }
        }
    }

    for (const [id, want] of Object.entries(REFERENCE_SEVERITY)) {
        const got = seen.get(id);

        if (got && got !== want) {
            fails.push(`${id} is ${got}, but the reference calls it ${want}`);
        }
    }

    return fails;
}

// A Duplex result value must carry the warning colour, as the Single ones do.
//
// The Duplex results block hardcoded class="se-value" while the Single block
// used t-att-class="valueClass", so Duplex numbers stayed green no matter what
// the Error Manager said. The panel and the colour came from the same
// warningLevel and disagreed on screen.
//
// This checks the getter rather than the markup, because that is what the
// template binds to - and it checks all three states, since a getter that
// always returned red would pass a one-sided test.
function duplexValuesCarryWarningColour(mod) {
    const fails = [];
    // These three moved when the severities were corrected against the
    // reference, and the invariant caught it - which is the point of checking
    // every level rather than one.
    const cases = [
        // nothing to report
        { want: "se-value", st: { weight: "400", springs: 2,
            drum: "CANIMEX/TF D525-216", doorHeightFeet: 8 } },
        // yellow: over cone capacity and past both wire bands, all of which
        // the reference calls warnings - the springs are still sellable
        { want: "se-value se-value-yellow", st: { weight: "1400", springs: 1,
            drum: "CANIMEX/TF D525-216", doorHeightFeet: 8 } },
        // red: taller than the drum will take, which the reference calls an
        // error because it has to clamp the height to answer at all
        { want: "se-value se-value-red", st: { weight: "280", springs: 2,
            drum: "CANIMEX/TF D400-96", doorHeightFeet: 12 } },
    ];

    for (const c of cases) {
        const comp = duplex(mod, { cycles: "10,000", radius: "15",
            doorWidthFeet: 16, ...c.st });

        if (comp.valueClass !== c.want) {
            fails.push(
                `${c.st.drum} ${c.st.weight}lb ${c.st.springs}spr: valueClass is ` +
                `"${comp.valueClass}", expected "${c.want}"`
            );
        }
    }

    return fails;
}

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

// The price column must add up, and it must scale the way it was quoted to
// us: labour once, cones per spring, steel per pound of every spring.
//
// The total is the one number anybody reads, and it is the easiest to get
// silently wrong - round each part and sum, or sum and round once, and the
// column stops adding up by a cent. So the total is checked against its own
// parts rather than against a figure computed here a second way.
//
// The scaling checks are what catch a wrong basis. Doubling the spring count
// must double the cones and the steel and leave labour alone; if cones were
// ever charged once per assembly, or steel on a single spring, these fail.
function priceAddsUp(mod) {
    const fails = [];
    const states = [
        { assembly: "Single", springId: '2 5/8"' },
        { assembly: "Single", springId: '3 3/4"' },
        { assembly: "Single", springId: '5 1/4"' },
        { assembly: "Duplex", springId: '3 3/4" inside 6"' },
        { assembly: "Duplex", springId: '2 5/8" inside 5 1/4"' },
    ];

    for (const st of states) {
        for (const springs of [1, 2, 3, 4]) {
            for (const weight of ["300", "600", "1000"]) {
                const c = duplex(mod, { ...st, springs, weight });
                const label = `${st.assembly} ${st.springId} x${springs} @${weight}lb`;
                const parts = c.priceLabor + c.priceCones + c.priceSteel;

                if (Math.abs(c.priceTotal - parts) > 1e-9) {
                    fails.push(`${label}: total ${c.priceTotal} but parts sum to ${parts.toFixed(2)}`);
                }

                for (const [name, v] of [["labor", c.priceLabor], ["cones", c.priceCones],
                                         ["steel", c.priceSteel], ["total", c.priceTotal]]) {
                    if (!(v >= 0) || !isFinite(v)) {
                        fails.push(`${label}: ${name} is ${v}`);
                    }

                    if (Math.abs(v * 100 - Math.round(v * 100)) > 1e-9) {
                        fails.push(`${label}: ${name} ${v} is not a whole number of cents`);
                    }
                }
            }
        }

        // Cones and steel are per spring; labour is not.
        const one = duplex(mod, { ...st, springs: 1, weight: "600" });
        const two = duplex(mod, { ...st, springs: 2, weight: "600" });

        if (Math.abs(two.priceCones - 2 * one.priceCones) > 1e-9) {
            fails.push(`${st.assembly} ${st.springId}: cones ${one.priceCones} at one spring but ${two.priceCones} at two - not per spring`);
        }

        if (two.priceLabor !== one.priceLabor) {
            fails.push(`${st.assembly} ${st.springId}: labour changed with the spring count`);
        }

        // Steel follows the assembly weight, which doubles with the count at
        // a fixed per-spring weight - so compare against the weight rather
        // than assuming the per-spring figure is unchanged.
        for (const c of [one, two]) {
            const want = Math.round(c.assemblyWeight * 1.46 * 100) / 100;

            if (Math.abs(c.priceSteel - want) > 1e-9) {
                fails.push(`${st.assembly} ${st.springId} x${c.state.springs}: steel ${c.priceSteel} but ${c.assemblyWeight.toFixed(2)} lb at 1.46 is ${want}`);
            }
        }
    }

    return fails;
}

// The Single assembly length must reproduce the reference's own width
// brackets. The reference warns when the assembly exceeds the door width, and
// the width is an input, so sweeping it an inch at a time brackets the length
// to the inch without the reference ever reporting it.
//
// Measured on 575-120, 7'0", 60" hi-lift, 2 5/8", 200 lb (dev/pulled-s2.json,
// 72 readings). These are what pin ASSEMBLY_HARDWARE, which was a flat 24"
// fitted from two readings whose inputs were never written down - so it could
// not be re-derived, and it was wrong at every spring count.
//
// FOUR SPRINGS IS LEFT OUT. The reference warns at every width up to 125,
// so its assembly is over 125"; ours is 122.4" and would not warn at 123-125.
// That gap is not the hardware - it is the wire: at four springs the reference
// picks 0.207" where we pick 0.2", because our cycle life for 0.2" comes to
// 10,374 against a 10,000 target and the reference puts it below. Its length
// at 0.207" is 24", which is exactly ours, so only the cycle figure is out,
// by about 4% right at the threshold. Asserting the bracket here would pin
// the blame on the wrong constant.
function singleAssemblyBrackets(mod) {
    const fails = [];

    // springs -> [widest width the reference WARNS at, narrowest it does NOT]
    // null means that side was outside the swept window.
    const BRACKETS = { 1: [null, 80], 2: [110, 111], 3: [117, 118] };

    for (const [springs, [warnAt, fitsAt]] of Object.entries(BRACKETS)) {
        for (const [width, shouldWarn] of [[warnAt, true], [fitsAt, false]]) {
            if (width === null) {
                continue;
            }

            const c = make(mod, {
                assembly: "Single", drum: "CANIMEX/TF 575-120", springId: '2 5/8"',
                liftType: "Hi-Lift", liftin: "60",
                doorHeightFeet: 7, doorHeightInches: 0,
                cycles: "10,000", springs: Number(springs), radius: "15",
                weight: "200",
                doorWidthFeet: Math.floor(width / 12), doorWidthInches: width % 12,
            });

            // The app picks the wire in a useEffect the harness stubs out, so
            // drive it here or every case computes on the 0.25" default.
            const wire = c.recommendedWire;

            if (wire !== null && wire !== undefined) {
                c.state.wireSize = `${wire}"`;
            }

            const warns = (c.warnings ?? []).some((w) => w.id === "assembly-too-long");

            if (warns !== shouldWarn) {
                fails.push(
                    `${springs} spring(s) at ${width}" wide: reference ` +
                    `${shouldWarn ? "warns" : "fits"}, we ` +
                    `${warns ? "warn" : "fit"} (assembly ${c.assemblyLengthExact.toFixed(2)}")`
                );
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
    { name: "each warning's severity matches the reference", run: severityMatchesReference },
    { name: "Duplex result values carry the warning colour", run: duplexValuesCarryWarningColour },
    { name: "the cycles-low flag stays a caution, not a verdict", run: cyclesLowStaysCaution },
    { name: "Duplex raises no Wire-Size-dropdown warning", run: noStaleWireWarnings },
    { name: "no Duplex output depends on the Wire Size dropdown", run: duplexIgnoresWireDropdown },
    { name: "the price column adds up and scales per spring", run: priceAddsUp },
    { name: "Single assembly length matches the reference's width brackets", run: singleAssemblyBrackets },
];
