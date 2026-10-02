// Pull readings from the reference calculator straight into corpus shape.
//
//   node dev/pull.mjs <sweeps.json> [out.json]
//
// CREDENTIALS come from ~/.ssc-credentials, never from the command line, the
// environment of a shell you did not start, or this repository. Two lines:
//
//   username=you@example.com
//   password=...
//
//   chmod 600 ~/.ssc-credentials
//
// That file is outside the repo and the output file is gitignored, so nothing
// secret can reach GitHub. The script prints neither value, ever.
//
// WHY THIS EXISTS. Every open question in the Duplex model is of the form "I
// need eight readings on one rung". By hand that is an evening; here it is
// eight requests. The analysis was never the bottleneck.
//
// IT IS DELIBERATELY SLOW - one request a second, and it refuses to run more
// than MAX_REQUESTS in one go. This is someone else's server and your account.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync, mkdtempSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

const BASE = "https://shop.servicespring.com";
const DELAY_MS = 1000;
const MAX_REQUESTS = 400;
const UA = "Mozilla/5.0 (X11; Linux x86_64) spring_engineering/dev-pull";

function creds() {
    const path = join(homedir(), ".ssc-credentials");

    if (!existsSync(path)) {
        console.error(
            `No ${path}.\n\n` +
            "Create it with two lines and nothing else:\n" +
            "  username=you@example.com\n" +
            "  password=...\n\n" +
            "then:  chmod 600 ~/.ssc-credentials"
        );
        process.exit(1);
    }

    const out = {};

    for (const line of readFileSync(path, "utf8").split("\n")) {
        const m = line.match(/^\s*(username|password)\s*=\s*(.+?)\s*$/);

        if (m) {
            out[m[1]] = m[2];
        }
    }

    if (!out.username || !out.password) {
        console.error(`${path} must contain both username= and password= lines.`);
        process.exit(1);
    }

    return out;
}

const jar = join(mkdtempSync(join(tmpdir(), "ssc-")), "cookies.txt");

function curl(args) {
    return execFileSync("curl", [
        "-sS", "--compressed", "-A", UA,
        "-b", jar, "-c", jar,
        ...args,
    ], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
}

function login() {
    const page = curl(["-L", `${BASE}/login`]);
    // the real form, not the header widget - its _token is the populated one
    const tokens = [...page.matchAll(/name="_token"\s+value="([^"]+)"/g)].map((m) => m[1]);

    if (!tokens.length) {
        throw new Error("no CSRF _token on the login page - the form may have changed");
    }

    const { username, password } = creds();
    const body = curl([
        "-L", "-X", "POST", `${BASE}/login`,
        "--data-urlencode", `_token=${tokens[tokens.length - 1]}`,
        "--data-urlencode", `username=${username}`,
        "--data-urlencode", `password=${password}`,
        "--data-urlencode", "redirectUri=",
        "-w", "\n%{url_effective}",
    ]);

    if (/\/login\s*$/.test(body.trim().split("\n").pop() || "")) {
        throw new Error("login rejected - check ~/.ssc-credentials");
    }

    console.log("authenticated");
}

// our vocabulary -> the calculator's query parameters
function query(c) {
    const p = new URLSearchParams();

    p.set("garageDoorLineId", c.garageDoorLineId);
    p.set("assembly", c.assembly ?? "Duplex");
    p.set("lift", c.lift ?? "Standard");
    p.set("radius", String(c.radius ?? 15));
    p.set("numberOfSprings", String(c.springs ?? 2));
    p.set("drumName", c.drum);
    p.set("cycles", String(c.cycles ?? 10000));
    p.set("doorWidthInches", String(c.widthInches ?? 108));
    p.set("doorHeightInches", String(c.heightInches));
    p.set("doorWeightPounds", String(c.weight));

    if ((c.assembly ?? "Duplex") === "Duplex") {
        p.set("duplexInnerSpringInnerDiameter", String(c.innerId ?? 3.75));
        p.set("duplexOuterSpringInnerDiameter", String(c.outerId ?? 6));
    }

    // hi-lift: the parameter name is not yet confirmed, so send the ones it
    // might be and let the server ignore the rest. Confirm against a reading
    // taken by hand before trusting any hi-lift pull.
    if (c.highLiftInches !== undefined) {
        for (const k of ["highLiftInches", "highLift", "liftInches"]) {
            p.set(k, String(c.highLiftInches));
        }
    }

    for (const [k, v] of Object.entries(c.extra ?? {})) {
        p.set(k, String(v));
    }

    return p.toString();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const [sweepFile, outFile = "dev/pulled.json"] = process.argv.slice(2);

if (!sweepFile) {
    console.error("usage: node dev/pull.mjs <sweeps.json> [out.json]");
    process.exit(1);
}

const cases = JSON.parse(readFileSync(sweepFile, "utf8"));

if (cases.length > MAX_REQUESTS) {
    console.error(`${cases.length} cases exceeds the ${MAX_REQUESTS} cap. Split it.`);
    process.exit(1);
}

login();

const results = [];

for (let i = 0; i < cases.length; i++) {
    const c = cases[i];
    const url = `${BASE}/spring-engineering/engineer-torsion-spring?${query(c)}`;
    let parsed = null;
    let raw = "";

    try {
        raw = curl(["-L", url]);
        parsed = JSON.parse(raw);
    } catch {
        parsed = null;
    }

    if (!parsed) {
        console.log(`${i + 1}/${cases.length}  ${c.label ?? ""}  NOT JSON - session may have expired`);
        results.push({ input: c, error: "non-JSON response", bodyHead: raw.slice(0, 200) });
    } else {
        const d = parsed.data ?? {};
        const inner = d.innerSpring ?? {};
        const outer = d.outerSpring ?? {};
        console.log(
            `${i + 1}/${cases.length}  ${(c.label ?? "").padEnd(28)} ` +
            `${outer.wireSize ?? "?"}/${inner.wireSize ?? "?"}  ` +
            `L ${inner.springLength ?? "?"}  cyc ${d.cycles ?? "?"}  ${parsed.status}`
        );
        results.push({ input: c, status: parsed.status, messages: parsed.messages, data: d });
    }

    if (i < cases.length - 1) {
        await sleep(DELAY_MS);
    }
}

writeFileSync(outFile, JSON.stringify(results, null, 1) + "\n");
console.log(`\n${results.length} result(s) -> ${outFile}`);
