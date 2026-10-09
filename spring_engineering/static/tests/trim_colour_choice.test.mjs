// Unit test for the Trims colour choice.
//
//   node garage_door_supply/static/tests/trim_colour_choice.test.mjs
//
// Plain node against a minimal DOM shim - no jsdom, no browser. There is a
// Chrome binary in the build but it would not run headless here, and a test
// that cannot be run is not a test. The shim covers only what swap() touches,
// and it imports the SHIPPED file rather than a copy, so the thing under test
// is the thing that is served.
//
// WHAT IT CANNOT TELL YOU. That Odoo creates the input in the first place -
// that comes from the attribute value being flagged "Custom value", and is
// verified by reading website_sale's own handleCustomValues, which sets the
// input's placeholder to the attribute value's name and is why matching on the
// placeholder works. And that the cart stores it, which it does because
// _getCustomPTAVValues collects every `.variant_custom_value` and reads its
// `.value` - true of a <select> exactly as of an <input>.
// Minimal DOM shim, enough for the real swap() to run.
class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this._attrs = new Map(); this.dataset = {}; this.children = [];
    this.parent = null; this._value = "";
    const s = new Set();
    this.classList = { _s: s, add: (...c) => c.forEach((x) => s.add(x)), contains: (c) => s.has(c) };
  }
  get className() { return [...this.classList._s].join(" "); }
  setAttribute(k, v) { this._attrs.set(k, String(v)); }
  getAttribute(k) { return this._attrs.has(k) ? this._attrs.get(k) : null; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  replaceWith(n) { const p = this.parent; p.children[p.children.indexOf(this)] = n; n.parent = p; }
  get options() { return this.children.filter((c) => c.tagName === "OPTION"); }
  get value() { return this._value; }
  set value(v) {
    if (this.tagName === "SELECT") { if (this.options.some((o) => o.value === v)) this._value = v; return; }
    this._value = v;
  }
}
class FakeInput extends El { constructor() { super("input"); } }
globalThis.HTMLInputElement = FakeInput;
globalThis.Node = { ELEMENT_NODE: 1 };
globalThis.MutationObserver = class { observe() {} };
globalThis.document = { readyState: "complete", body: { querySelectorAll: () => [] },
  createElement: (t) => new El(t), addEventListener: () => {} };

// Imported as a data: URL module. The shipped file is plain .js, which node
// treats as CommonJS without a package.json saying otherwise, so a direct
// import of it fails on `export`. Reading the real file and evaluating its real
// text as a module keeps this a test of what is served, with no package.json
// dropped into an asset directory to confuse the bundler.
const { readFileSync } = await import("node:fs");
const { fileURLToPath } = await import("node:url");
const { dirname, join } = await import("node:path");
const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src", "js", "trim_colour_choice.js");
const { swap, choicesFor } = await import(
    "data:text/javascript," + encodeURIComponent(readFileSync(SRC, "utf8"))
);

let pass = 0, fail = 0;
const ok = (n, c, got = "") => { c ? (pass++, console.log(`  PASS  ${n}`)) : (fail++, console.log(`  FAIL  ${n} :: ${got}`)); };

function box(placeholder, ptav = "77", value = "") {
  const li = new El("li");
  const i = new FakeInput();
  i.setAttribute("placeholder", placeholder);
  i.dataset.customProductTemplateAttributeValueId = ptav;
  i.classList.add("variant_custom_value", "custom_value_radio", "form-control", "mt-2");
  i._value = value;
  li.appendChild(i);
  return { li, i };
}

// 1. Trims becomes a select of the three colours
let { li, i } = box("Trims", "501");
swap(i);
let w = li.children[0];
ok("Trims -> SELECT", w.tagName === "SELECT", w.tagName);
ok("three colours plus a blank prompt",
   JSON.stringify(w.options.map((o) => o.value)) === JSON.stringify(["", "Black", "Bronze", "White"]),
   JSON.stringify(w.options.map((o) => o.value)));
ok("keeps the class the cart looks for", w.classList.contains("variant_custom_value"), w.className);
ok("keeps the attribute-value id", w.dataset.customProductTemplateAttributeValueId === "501",
   w.dataset.customProductTemplateAttributeValueId);
ok("starts unselected so a colour must be chosen", w.value === "", `"${w.value}"`);

// 2. the other extras are left exactly as they were
({ li, i } = box("Struts", "502"));
swap(i);
ok("Struts left as a text input", li.children[0] === i && li.children[0].tagName === "INPUT",
   li.children[0].tagName);

// 3. singular spelling also matches
({ li, i } = box("Trim", "503"));
swap(i);
ok("singular 'Trim' also matches", li.children[0].tagName === "SELECT", li.children[0].tagName);

// 4. a colour already chosen survives a re-render, case-insensitively
({ li, i } = box("Trims", "501", "bronze"));
swap(i);
ok("restores a previously chosen colour", li.children[0].value === "Bronze", li.children[0].value);

// 5. an unrelated name is not touched, and an unknown value is not restored
ok("choicesFor('Windows') is null", choicesFor("Windows") === null, String(choicesFor("Windows")));
({ li, i } = box("Trims", "501", "purple"));
swap(i);
ok("a colour that is not offered is dropped", li.children[0].value === "", `"${li.children[0].value}"`);

console.log(`\n${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
