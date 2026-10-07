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

// STUBS ARE BUILT FROM THE FILE'S OWN IMPORT STATEMENTS, not written down
// here. This used to be a fixed block declaring the four names the component
// happened to use, which made the harness blind to the one thing it is in the
// best position to check: whether every name the source USES it also IMPORTS.
//
// It missed exactly that. `onWillStart` was called in setup() and never added
// to the owl import, and the page threw "onWillStart is not defined" on the
// first mount in production. Nothing here could see it - the harness never
// called setup(), and even if it had, a hardcoded stub block would have
// supplied the name the real module was missing and the test would have
// passed. A stub list that is independent of the import list cannot test the
// import list.
//
// So: the names come from the source, and anything imported that is not in
// the table below is a hard error rather than a silent undefined. None of
// these affect arithmetic - useState is identity because nothing re-renders,
// useEffect is a no-op because the wire auto-pick is driven explicitly, and
// onWillStart just collects its callbacks so a test can run them.
const STUB_TABLE = {
    "@odoo/owl": {
        Component: "class {}",
        useState: "(o) => o",
        useEffect: "() => {}",
        onWillStart: "(cb) => { __test.willStart.push(cb); }",
        onMounted: "(cb) => { __test.mounted.push(cb); }",
        onWillUnmount: "() => {}",
        useRef: "() => ({ el: null })",
        useComponent: "() => null",
    },
    "@web/core/registry": {
        registry: "{ category: () => ({ add: () => {} }) }",
    },
    "@web/core/network/rpc": {
        rpc: "(...args) => __test.rpc(...args)",
    },
};

// What a test can reach into: the collected lifecycle callbacks, and the rpc
// the component will call. The default rpc THROWS rather than returning
// something plausible, so a test that forgets to install one fails loudly
// instead of quietly measuring a component that got no server data.
const TEST_HOOKS = `
const __test = {
    willStart: [],
    mounted: [],
    rpc: async (route) => {
        throw new Error(\`no rpc stub installed for \${route}\`);
    },
};
`;

function stubsFor(src) {
    const lines = [];
    const seen = [];

    for (const m of src.matchAll(/^import\s*\{([^}]*)\}\s*from\s*"([^"]+)"\s*;/gm)) {
        const names = m[1].split(",").map((n) => n.trim()).filter(Boolean);
        const table = STUB_TABLE[m[2]];

        if (!table) {
            throw new Error(
                `dev/harness.mjs has no stubs for "${m[2]}". Add them to STUB_TABLE ` +
                "rather than letting the import vanish."
            );
        }

        for (const name of names) {
            if (!(name in table)) {
                throw new Error(
                    `dev/harness.mjs has no stub for ${name} from "${m[2]}". Add one to ` +
                    "STUB_TABLE - a missing stub means the suite runs against a " +
                    "different module than the browser does."
                );
            }

            seen.push(name);
            lines.push(`const ${name} = ${table[name]};`);
        }
    }

    return { code: TEST_HOOKS + lines.join("\n") + "\n", names: seen };
}

const EXPORTS = `
export {
    SpringEngineering, defaultState,
    DUPLEX_PAIRS, DUPLEX_ALIASES, duplexLength,
    WIRE_SIZES, WIRE_LIMITS, DRUMS, DRUM_LIMITS, HILIFT_DRUMS, drumTurns,
    TORSION_CONSTANT, CYCLE_COEFFICIENT, CYCLE_WIRE_EXPONENT, CYCLE_EXPONENT,
    DUPLEX_ACCEPT_FRACTION, duplexActiveLength, duplexPairBalanced,
    CONE_PRICES, STEEL_PRICE_PER_LB, normaliseRates,
    __test,
};
`;

export async function load() {
    const src = readFileSync(SOURCE, "utf8");
    const code =
        stubsFor(src).code +
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

// A component that has been SET UP, which `make` deliberately does not do.
//
// `make` assigns state directly and skips setup(), because the 8,000-reading
// replay does not need lifecycle hooks and is faster without them. That is
// also why a missing import in setup() survived every test in this
// repository: the one function the browser always calls was the one function
// nothing here called.
//
// Pass `rpc` to answer the component's own fetch. The willStart callbacks are
// awaited, so this returns a component in the state the first render sees.
export async function mount(mod, overrides = {}, { rpc } = {}) {
    mod.__test.willStart.length = 0;
    mod.__test.mounted.length = 0;

    if (rpc) {
        mod.__test.rpc = rpc;
    }

    const component = new mod.SpringEngineering();

    component.setup();
    Object.assign(component.state, overrides);

    for (const cb of mod.__test.willStart) {
        await cb();
    }

    return component;
}
