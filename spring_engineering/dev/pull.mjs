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

// SSC_BASE exists so the failure handling below can be tested against a server
// that is deliberately broken, without touching the real one. It is a test
// seam and nothing else - leave it unset and this is unchanged.
const BASE = process.env.SSC_BASE || "https://shop.servicespring.com";
// One request a second by default. PULL_DELAY_MS can only make it SLOWER.
// Asking faster is never the fix for anything here - this is someone else's
// server and the account - so the floor is not negotiable.
const DELAY_MS = Math.max(1000, Number(process.env.PULL_DELAY_MS) || 1000);
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

// A LOST SESSION WOULD OTHERWISE THROW AWAY EVERY REMAINING REQUEST.
//
// If the cookie jar expires partway through a long pull the server stops
// answering with JSON and answers with the login page - HTML, status 200. The
// loop below caught the JSON.parse failure, recorded "non-JSON response", and
// would then ask an unauthenticated server every remaining question. So a
// non-JSON body is now treated as "log in again and ask once more".
//
// BUT AN HTML BODY IS USUALLY NOT A LOST SESSION, AND ASSUMING IT WAS COST AN
// HOUR. A run of 200 came back with 48 HTML bodies and the obvious reading was
// expiry: they began at reading 123 and never recovered. They were NOT
// contiguous, which should have been the tell, and a fresh login did not fix
// them. Every one of the 48 was a STANDARD-lift request against 525-54HL,
// 575-120 or D800-120 - hi-lift drums, which answer only when lift=HiLift and
// serve an HTML page otherwise. 0 of 48 such requests returned JSON; 120 of
// 120 of the same three drums under HiLift did. The combination was
// impossible, and no amount of logging in was ever going to help.
//
// Hence RELOGIN_CAP: when the far end keeps serving HTML the likeliest
// explanation is that the REQUEST is wrong, not the session, and retrying is a
// slow way to hammer someone else's server. Read what is being ASKED before
// concluding anything about the cookie.
const RELOGIN_CAP = 5;
let relogins = 0;

// BACK OFF WHEN THE FAR END STOPS ANSWERING, AND GIVE UP IF IT KEEPS NOT
// ANSWERING.
//
// Batch V9 spent 124 requests on nothing. The server began returning HTML
// instead of JSON part way in - interleaved across every drum and both lift
// types, so not an impossible combination - the re-login fired its five
// attempts, and then the loop marched through the rest of the sweep at a
// request a second collecting error pages. It recovered on its own later, which
// is the signature of a transient limit on their side, not of anything wrong
// with the request.
//
// Hammering a server that is already refusing is the one thing a polite
// scraper must not do. So consecutive failures now sleep for longer and longer,
// and after GIVE_UP of them in a row the run stops and keeps what it has.
// Stopping loses nothing: results are flushed after every reading, and
// dev/rung-target-sample.mjs dedupes against what is already on disk, so the
// unpulled remainder simply turns up in the next batch.
const BACKOFF_MAX_MS = 60000;
// PULL_GIVE_UP exists so the give-up path can be exercised in seconds instead
// of twenty minutes; the default is what matters.
const GIVE_UP = Number(process.env.PULL_GIVE_UP) || 25;
let consecutiveBad = 0;

function looksLikeHtml(body) {
    return /^\s*(<!DOCTYPE|<html)/i.test(body);
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

    // Hi-lift. The parameter is `hiLift`, in inches, and the lift type is
    // "HiLift" with no hyphen - both confirmed from a request the calculator
    // itself issued. Eight guessed names had failed before that; the lesson is
    // that one real request beats any amount of probing.
    if (c.hiLift !== undefined) {
        p.set("hiLift", String(c.hiLift));
    }

    // Single carries its spring ID as `innerDiameter`, where Duplex uses the
    // two duplex* parameters above.
    if ((c.assembly ?? "Duplex") === "Single" && c.innerDiameter !== undefined) {
        p.set("innerDiameter", String(c.innerDiameter));
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

// AN EVALUATION DRAW MUST NOT LAND ON A NAME THE FITTER WILL INGEST.
//
// dev/derive.mjs reads every dev/pulled*.json and skips only those whose NAME
// matches /(^|-)(eval|rand|biased)/. That has gone wrong before - a uniform
// sample drawn to SCORE the model was folded into the fit by every apply.sh,
// and the score climbed from 57.5% to 91.9% while the gain was attributed to a
// fitter change. The model was being measured on rows it had just trained on.
//
// A filename is a weak place to carry something that matters this much, so
// dev/eval-sample.mjs stamps `eval: true` on every case it generates and this
// refuses to write those cases anywhere the fitter would read them. The check is
// on the DATA, which cannot be mistyped.
const isEvalDraw = cases.some((c) => c.eval === true);

if (isEvalDraw && !/(^|-)(eval|rand|biased)/.test(outFile.split("/").pop())) {
    console.error(
        `${sweepFile} is an evaluation draw - its cases carry eval: true - and\n`
        + `${outFile} is a name dev/derive.mjs would FIT rather than skip.\n\n`
        + "Evaluation readings folded into the fit make the model look good on\n"
        + "rows it was just trained on, which has already happened here once.\n\n"
        + "Use a name containing eval, for example dev/pulled-eval-<what>.json."
    );
    process.exit(1);
}

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

    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            raw = curl(["-L", url]);
            parsed = JSON.parse(raw);
            break;
        } catch {
            parsed = null;
        }

        // Second time round there is nothing left to try - fall through and
        // record the failure rather than logging in again on the way out.
        if (attempt > 0 || !looksLikeHtml(raw) || relogins >= RELOGIN_CAP) {
            break;
        }

        relogins += 1;
        console.log(`  session lost at ${i + 1}/${cases.length} - re-authenticating (${relogins}/${RELOGIN_CAP})`);
        await sleep(DELAY_MS);

        try {
            login();
        } catch (e) {
            console.log(`  re-login failed: ${e.message}`);
            break;
        }

        await sleep(DELAY_MS);
    }

    if (!parsed) {
        consecutiveBad += 1;
        console.log(`${i + 1}/${cases.length}  ${c.label ?? ""}  NOT JSON`
            + ` (${consecutiveBad} in a row)`);
        results.push({ input: c, error: "non-JSON response", bodyHead: raw.slice(0, 200) });
        writeFileSync(outFile, JSON.stringify(results, null, 1) + "\n");

        if (consecutiveBad >= GIVE_UP) {
            console.log(`\n${GIVE_UP} unanswered in a row - stopping and keeping`
                + ` the ${results.filter((r) => !r.error).length} readings already gathered.`
                + `\nThe rest of the sweep is simply unpulled; the next batch will pick it up.`);
            break;
        }

        // 2s, 4s, 8s ... capped. Deliberately slower than the steady rate.
        const wait = Math.min(BACKOFF_MAX_MS, 1000 * 2 ** Math.min(consecutiveBad, 6));

        console.log(`  backing off ${wait / 1000}s`);
        await sleep(wait);
    } else {
        consecutiveBad = 0;
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

    // Flush after every reading. A long pull that gets interrupted - lost
    // shell, compaction, Ctrl-C - used to lose every reading it had already
    // paid for. The server charge is the expensive part; the write is free.
    writeFileSync(outFile, JSON.stringify(results, null, 1) + "\n");

    if (i < cases.length - 1) {
        await sleep(DELAY_MS);
    }
}

writeFileSync(outFile, JSON.stringify(results, null, 1) + "\n");
console.log(`\n${results.length} result(s) -> ${outFile}`);
