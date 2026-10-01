// What to read off the reference calculator next, in priority order.
//
//   node dev/worklist.mjs [drum-substring]
//
// WHY A WORKLIST AND NOT JUST "TAKE MORE READINGS".
//
// The length rule floors to the whole inch, so a reading taken anywhere in
// the middle of a step tells you almost nothing: it only says C lies
// somewhere inside a bracket a whole inch wide, which is +/-3% or worse. The
// git history is full of refits that each fixed one case and broke another,
// and this is why - the constants were bracket MIDPOINTS, and the midpoint of
// a loose bracket is a guess.
//
// A PAIR OF READINGS EITHER SIDE OF A STEP is worth far more than ten
// readings away from one. The file's own comment says it ("A BOUNDARY IS
// WORTH MORE THAN A READING") and then mostly does not do it. Each halving of
// the weight gap halves the bracket on C.
//
// HOW MUCH PRECISION IS NEEDED. Measured over the D400-144 grid, a C error of
// 0.1% moves 2.4% of lengths by a full inch, and 1% moves 22.7% of them. So C
// has to be right to about 0.01-0.05%, which a 1 lb straddle at ~500 lb
// delivers and a scattered reading never will.
//
// HOW TO USE IT. Take the rows for one combination, enter them in the
// reference calculator, and write down the inner length it reports. Stop at
// the first row where the reference disagrees with the prediction - that row
// IS the measurement, and the implied C bracket is printed with it. Then add
// both sides of the step to dev/corpus.json as 'verified' readings.
import { load, make } from "./harness.mjs";

const DRUM = process.argv[2] || "D400-144";

// Where each combination gets selected, so a straddle lands on the pair we
// actually mean to calibrate rather than its neighbour.
const PLANS = [
    { springId: '3 3/4" inside 6"', heights: [7, 10, 13], targets: ["10,000", "25,000"] },
    { springId: '2 5/8" inside 5 1/4"', heights: [7, 10], targets: ["10,000"] },
];

function lengthAt(mod, state) {
    const component = make(mod, { assembly: "Duplex", springs: 2, radius: "15", ...state });
    const step = component.duplexStep;

    return step
        ? {
              wire: `${step.outerWire}/${step.innerWire}`,
              length: component.duplexInnerLength,
              tippt: component.tipptExact,
              C: step.C,
              tau: step.tau,
              measured: step.measured,
          }
        : null;
}

// Every C consistent with the step seen between loW and hiW. Scanned rather
// than solved: the rule has a regime switch in it, so an analytic inverse
// would need casework that a scan makes unnecessary.
function bracketC(mod, base, loW, hiW, loLen, hiLen, tau) {
    const a = lengthAt(mod, { ...base, weight: String(loW) });
    const b = lengthAt(mod, { ...base, weight: String(hiW) });

    if (!a || !b) {
        return null;
    }

    const centre = a.C;
    let min = null;
    let max = null;

    for (let C = centre * 0.9; C <= centre * 1.1; C += centre * 0.00002) {
        if (
            mod.duplexLength(C / a.tippt) === loLen &&
            mod.duplexLength(C / b.tippt) === hiLen
        ) {
            if (min === null) {
                min = C;
            }

            max = C;
        }
    }

    return min === null ? null : { min, max, width: ((max - min) / centre) * 100 };
}

const mod = await load();
const drumName = Object.keys(mod.DRUMS).find((d) => d.includes(DRUM));

if (!drumName) {
    console.log(`No standard drum matching "${DRUM}". Known: ${Object.keys(mod.DRUMS).join(", ")}`);
    process.exit(1);
}

console.log(`\nMEASUREMENT WORKLIST - ${drumName}`);
console.log("Read the inner spring length the reference reports for each row.");
console.log("Stop at the first row that disagrees; that row is the measurement.\n");

let block = 0;

for (const plan of PLANS) {
    for (const height of plan.heights) {
        for (const cycles of plan.targets) {
            const base = { drum: drumName, springId: plan.springId, doorHeightFeet: height, cycles };
            const steps = [];
            let prev = null;

            // 1 lb resolution: finer than the reference's own weight input is
            // worth reading, and enough to pin C to ~0.2% before refining.
            for (let w = 150; w <= 1000; w++) {
                const now = lengthAt(mod, { ...base, weight: String(w) });

                if (!now) {
                    continue;
                }

                if (prev && now.wire === prev.wire && now.length !== prev.length) {
                    steps.push({ at: w, from: prev, to: now });
                }

                prev = now;
            }

            // One straddle per wire combination is enough to pin its C; extra
            // steps on the same combination only re-measure the same constant.
            const perWire = new Map();

            for (const s of steps) {
                if (!perWire.has(s.to.wire)) {
                    perWire.set(s.to.wire, s);
                }
            }

            for (const [wire, s] of perWire) {
                const bracket = bracketC(mod, base, s.at - 1, s.at, s.from.length, s.to.length, s.to.tau);

                block++;
                console.log(
                    `${String(block).padStart(2)}. ${wire}  ${plan.springId}  ` +
                    `${height}'0", 2 springs, radius 15", target ${cycles}` +
                    (s.to.measured ? "" : "   [C IS AN ESTIMATE - highest value]")
                );
                console.log(
                    `    C now ${s.to.C.toFixed(1)}` +
                    (bracket
                        ? `   this straddle pins it to [${bracket.min.toFixed(1)}, ${bracket.max.toFixed(1)}] = +/-${(bracket.width / 2).toFixed(3)}%`
                        : "   (bracket not resolvable at this step)")
                );
                console.log(`    predicts the length steps ${s.from.length}" -> ${s.to.length}" between ${s.at - 1} and ${s.at} lb`);

                for (const w of [s.at - 3, s.at - 1, s.at, s.at + 2]) {
                    const r = lengthAt(mod, { ...base, weight: String(w) });

                    if (r && r.wire === wire) {
                        console.log(`       ${String(w).padStart(4)} lb  ->  predicts ${r.length}"`);
                    }
                }

                console.log("");
            }
        }
    }
}

console.log(`${block} straddle(s). Each needs 2-4 readings; a disagreement on any row is`);
console.log("worth more than a row that confirms. Record both sides in dev/corpus.json.\n");
