// ONE mapping from a reference reading to the component's state.
//
// WHY THIS EXISTS. Every tool that scores the model has to turn a pulled
// reading back into the inputs the component expects, and that translation is
// not obvious: the reference reports a track radius of 10 where the dropdown
// says "LHR", and its cycle target is a number where the dropdown holds a
// formatted string. Four copies of this mapping existed. They did not agree,
// and one of them was wrong:
//
//   - dev/clean-cases.mjs used the reading's own door width
//   - dev/realistic.mjs hardcoded 9 ft
//   - dev/miss-profile.mjs hardcoded 18 ft
//   - a diagnostic written later mapped radius 12 to '12"' instead of "12"
//
// The last one cost an hour. An unrecognised radius falls back to a default
// rather than failing, so the tool reported 60.3% clean length where the
// scorer reported 93.7%, and it looked exactly like a model bug localised to
// standard lift - which is where the radius matters. It was only caught
// because the two numbers were compared.
//
// THE LESSON IS THE RULE NOW: a tool that needs this mapping imports it. A
// tool that measures a number another tool already reports must be checked
// against that number before its findings are believed.
export const REF_RADIUS = { 10: "LHR", 12: "12", 15: "15" };

// The reading's own door width, in feet and inches. Width changes nothing
// about the spring; it decides only whether the assembly-too-long warning
// fires, which is why it was safe to hardcode and also why hardcoding it made
// two tools disagree about which readings the reference flags.
function widthOf(input) {
    const inches = input.widthInches ?? 108;

    return { doorWidthFeet: Math.floor(inches / 12), doorWidthInches: inches % 12 };
}

export function isHiLift(input) {
    return input.lift === "HiLift" || input.lift === "Hi-Lift";
}

// A reading the reference answered with no complaint of its own. These are the
// ones that get ordered, so they are scored separately everywhere.
export function isClean(reading) {
    const msgs = (reading.messages ?? []).filter((m) => !/contact us/i.test(m));

    return msgs.length === 0 && reading.status === "success";
}

// True for a Duplex reading on the 3 3/4" inside 6" pair, which is the only
// pair the model is fitted for.
export function isModelledDuplex(input) {
    return (input.assembly ?? "Duplex") === "Duplex" && Number(input.innerId) === 3.75;
}

export function stateFromReading(input) {
    const hi = isHiLift(input);

    return {
        assembly: "Duplex",
        drum: input.drum,
        springId: '3 3/4" inside 6"',
        springs: input.springs,
        radius: REF_RADIUS[Number(input.radius)] ?? String(input.radius),
        ...(hi ? { liftType: "Hi-Lift", liftin: String(input.hiLift) } : {}),
        cycles: Number(input.cycles).toLocaleString("en-US"),
        weight: String(input.weight),
        ...widthOf(input),
        doorHeightFeet: Math.floor(input.heightInches / 12),
        doorHeightInches: input.heightInches % 12,
    };
}
