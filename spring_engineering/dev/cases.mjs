// Input grids. Kept separate from the checks so a grid can be widened without
// touching the assertions.

export const STANDARD_DRUMS = [
    "CANIMEX/TF D400-96",
    "CANIMEX/TF D400-144",
    "CANIMEX/TF D525-216",
];

export const HILIFT_DRUMS = [
    "CANIMEX/TF 525-54HL",
    "CANIMEX/TF 575-120",
    "CANIMEX/TF D800-120",
];

// Spans the END_COILS_SMALL_ID / END_COILS_LARGE_ID split at 4.5".
export const SINGLE_IDS = ['1 3/4"', '2 5/8"', '3 3/4"', '4 3/8"', '5 1/4"', '6"'];

export const DUPLEX_IDS = [
    '3 3/4" inside 6"',
    '2 5/8" inside 5 1/4"',
    '3 1/2" inside 5 1/2" (Raynor)',
    '3 3/8" inside 5 7/8" (Overhead)',
];

export const TARGETS = ["10,000", "15,000", "25,000", "50,000", "100,000"];

// --- Single path -----------------------------------------------------------
// Broad enough to pin every Single branch: both end-coil regimes, all three
// standard drums and all three hi-lift drums, every radius, vertical lift,
// the pitch input, and a weight range that crosses the wire-recommendation
// steps. This grid is the contract that Duplex work must not disturb.
export function* singleCases() {
    for (const drum of STANDARD_DRUMS) {
        for (const springId of SINGLE_IDS) {
            for (const weight of ["150", "300", "500", "750"]) {
                for (const radius of ["12", "15", "LHR"]) {
                    for (const h of [7, 10, 14]) {
                        yield {
                            assembly: "Single", drum, springId, weight, radius,
                            doorHeightFeet: h, liftType: "Standard",
                        };
                    }
                }
            }
        }
    }

    for (const drum of HILIFT_DRUMS) {
        for (const liftin of ["0", "12", "36", "54"]) {
            for (const weight of ["200", "450"]) {
                for (const h of [7, 10]) {
                    yield {
                        assembly: "Single", drum, liftin, weight,
                        doorHeightFeet: h, liftType: "Hi-Lift", springId: '2 5/8"',
                    };
                }
            }
        }
    }

    for (const drum of STANDARD_DRUMS) {
        for (const weight of ["250", "600"]) {
            yield {
                assembly: "Single", drum, weight, liftType: "Vertical",
                doorHeightFeet: 9, springId: '3 3/4"',
            };
        }
    }

    for (const springs of [1, 2, 3, 4]) {
        for (const cycles of TARGETS) {
            yield {
                assembly: "Single", drum: "CANIMEX/TF D400-144", springs, cycles,
                weight: "500", springId: '2 5/8"', doorHeightFeet: 8,
            };
        }
    }

    for (const pitchAmount of ["0/12", "3/12", "6/12"]) {
        yield {
            assembly: "Single", drum: "CANIMEX/TF D400-144", pitch: true,
            pitchAmount, weight: "400", springId: '2 5/8"', doorHeightFeet: 9,
        };
    }
}

// The Single outputs that are snapshotted. Display getters AND the exact ones
// behind them, so a change that moves an intermediate but happens to round to
// the same string still shows up.
export const SINGLE_OUTPUTS = [
    "resultsVisible", "turns", "turnsExact", "multiplier", "multiplierExact",
    "tippt", "tipptExact", "rEffExact", "meanDiameter", "divider",
    "springTorque", "cycleLife", "recommendedWire", "springLengthExact",
    "springLength", "springWeight", "assemblyLengthExact", "assemblyLength",
    "warningLevel", "wireSizeVisible",
];
