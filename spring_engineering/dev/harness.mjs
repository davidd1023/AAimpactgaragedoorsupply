// Standalone loader for the calculator component, for use outside Odoo.
//
// WHY THIS EXISTS. The Duplex model is reverse-engineered from readings taken
// by hand off the manufacturer's reference calculator. Until this harness
// there was no way to re-run those readings, so every recalibration was blind
// and the git log is a sequence of refits that each traded one case for
// another. Nothing in here changes the app: it imports the SAME source file
// the manifest ships, with OWL stubbed out, so there is no second copy to
// drift.
//
// Run the suite with:   node dev/replay.mjs
//
// NOT loaded by __manifest__.py and not under static/, so Odoo never serves
// or bundles it.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

export const SOURCE = join(HERE, "..", "static", "src", "js", "spring_engineering.js");

// The component only ever uses these four imports, and none of them affect
// arithmetic: useState is identity because nothing here re-renders, and
// useEffect is a no-op because the wire auto-pick is driven explicitly.
const STUBS = `
const Component = class {};
const useState = (o) => o;
const useEffect = () => {};
const registry = { category: () => ({ add: () => {} }) };
`;

const EXPORTS = `
export {
    SpringEngineering, defaultState,
    DUPLEX_PAIRS, DUPLEX_ALIASES, duplexLength,
    WIRE_SIZES, WIRE_LIMITS, DRUMS, DRUM_LIMITS, HILIFT_DRUMS, drumTurns,
    TORSION_CONSTANT, CYCLE_COEFFICIENT, CYCLE_WIRE_EXPONENT, CYCLE_EXPONENT,
    DUPLEX_ACCEPT_FRACTION, duplexActiveLength, duplexPairBalanced,
    CONE_PRICES, STEEL_PRICE_PER_LB, normaliseRates,
};
`;

export async function load() {
    const src = readFileSync(SOURCE, "utf8");
    const code =
        STUBS +
        src
            .replace(/^\s*\/\*\*\s*@odoo-module\s*\*\*\/\s*$/m, "")
            .replace(/^import\s[^;]*;\s*$/gm, "")
            .replace(/^export class /m, "class ") +
        EXPORTS;

    const url =
        "data:text/javascript;base64," + Buffer.from(code, "utf8").toString("base64");

    return import(url);
}

// A component primed with one state. Defaults are the app's own defaults, so
// a case only states what it varies.
export function make(mod, overrides = {}) {
    const component = new mod.SpringEngineering();

    component.state = { ...mod.defaultState(), ...overrides };

    return component;
}
