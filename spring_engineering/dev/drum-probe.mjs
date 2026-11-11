// ASK THE REFERENCE HOW IT PICKS A DRUM.
//
//   node dev/drum-probe.mjs            one request, to prove the endpoint
//   node dev/drum-probe.mjs list       the WHOLE drum table, one request
//   node dev/drum-probe.mjs sweep      map the recommendation rule over a grid
//
// WHY THIS EXISTS. "How is the drum picked" has been an open question for
// over a week - it blocks the second project's quoting automation, and
// nothing in this repository can derive it. It turns out the reference will
// simply answer: `common-components-*.js` on shop.servicespring.com names
//
//     GET /spring-engineering/drum-recommendation
//         ?liftType=&doorHeightInches=&doorWeightPounds=[&hiLift=]
//                                                      -> { drumName }
//
// THE HEADERS ARE NOT OPTIONAL, which cost two requests to learn. Without
// `X-Requested-With: XMLHttpRequest` the route redirects to /account and
// answers 200 with HTML - indistinguishable from an expired session. With it,
// the server answers JSON, including a 422 naming every field it wants. The
// field names come from that 422 rather than from reading the minified
// bundle, which showed `doorHeight` where the server wants
// `doorHeightInches`.
//
// beside the engineering endpoint `dev/pull.mjs` has always used. Nobody had
// ever asked it, because nobody had read their bundle.
//
// CREDENTIALS come from ~/.ssc-credentials only - never the command line, the
// environment, or this repository - exactly as dev/pull.mjs takes them, and
// neither value is ever printed.
//
// ONE REQUEST FIRST. Batch V16 spent 337 requests to learn what ten would
// have said; the default here is a single call and the sweep is opt-in.
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.SSC_BASE || "https://shop.servicespring.com";
const UA = "Mozilla/5.0 (X11; Linux x86_64) spring_engineering/dev-pull";
const jar = join(mkdtempSync(join(tmpdir(), "ssc-")), "cookies.txt");

function creds() {
    const path = join(homedir(), ".ssc-credentials");

    if (!existsSync(path)) {
        console.error(`No ${path}. See dev/pull.mjs for the format.`);
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

const curl = (args) => execFileSync("curl", [
    "-sS", "--compressed", "-A", UA, "-b", jar, "-c", jar, ...args,
], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });

// The same, as the page's own axios sends it. Login must NOT carry these.
const xhr = (args) => curl([
    "-H", "X-Requested-With: XMLHttpRequest", "-H", "Accept: application/json", ...args,
]);

function login() {
    const page = curl(["-L", `${BASE}/login`]);
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

const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

function recommend(heightInches, weightLb, hiLift) {
    const p = {
        liftType: hiLift ? "HiLift" : "Standard",
        doorHeightInches: String(heightInches),
        doorWeightPounds: String(weightLb),
    };

    if (hiLift) {
        p.hiLift = String(hiLift);
    }

    const q = new URLSearchParams(p);
    const raw = xhr(["-L", `${BASE}/spring-engineering/drum-recommendation?${q}`]);

    try {
        return JSON.parse(raw);
    } catch {
        return { error: raw.slice(0, 120) };
    }
}

login();

// THE WHOLE TABLE FOR ONE REQUEST, and it carries more than this repository
// has ever held: every drum's maximum height and weight (which DRUM_LIMITS
// records and which had to be measured), its moment arms, its circumference,
// and `maximumDiameter` - the MAXIMUM CABLE DIAMETER, which is the standing
// "does D800-120 run 1/4\" or 3/16\" cable" question answered outright.
if (process.argv[2] === "list") {
    // `liftType` is required here too, and it is how the STANDARD and
    // HI-LIFT sets are separated - this module keeps them in two tables
    // (DRUMS and HILIFT_DRUMS) and this is where that split comes from.
    for (const lift of ["Standard", "HiLift"]) {
    const raw = xhr(["-L", `${BASE}/spring-engineering/drum-list?liftType=${lift}`]);
    let rows;

    try { rows = JSON.parse(raw); } catch { console.log(raw.slice(0, 300)); process.exit(1); }

    // the payload is {"Drums": ["NAME", ...]} - NAMES ONLY, no records
    const all = rows.Drums || [];
    console.log(`\n=== ${lift}: ${all.length} drums ===`);
    for (const d of all) {
        console.log(`  ${d}`);
    }
    }
    process.exit(0);
}

if (process.argv[2] !== "sweep") {
    // The owner's own door: 14 ft, 1067 lb, standard lift. He already knows
    // the answer is D525-216, so this proves the endpoint rather than
    // discovering anything - the same way the first pull was proved.
    console.log(JSON.stringify(recommend(168, 1067, 0)));
    console.log("\nrun with `sweep` to map the rule.");
    process.exit(0);
}

// A GRID, one request a second, the same courtesy dev/pull.mjs observes.
const heights = [84, 96, 108, 120, 132, 144, 168, 192, 216];
const weights = [150, 250, 350, 450, 600, 800, 1000, 1200, 1500];
const rows = [];

for (const h of heights) {
    for (const w of weights) {
        const r = recommend(h, w, 0);
        rows.push({ h, w, drum: r.drumName ?? null, error: r.error });
        sleep(1000);
    }
    const line = weights.map((w) => {
        const d = rows.find((x) => x.h === h && x.w === w);
        return String(d?.drum ?? "-").replace(/^CANIMEX\/TF /, "").padEnd(12);
    }).join("");
    console.log(`${String(h).padStart(4)}"  ${line}`);
}

console.log("\nweights: " + weights.join(", "));
