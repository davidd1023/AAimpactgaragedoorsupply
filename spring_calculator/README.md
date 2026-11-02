# Spring Calculator

The torsion spring calculator, on its own, ready to go on a second Odoo
project.

It is **generated** from `spring_engineering` by
`tools/build_spring_calculator.py`. Nothing in here is written by hand except
this file and `tests/`.


## ⚠️ Never install this and `spring_engineering` in the same database

They claim the same routes — `/spring-calculator` and
`/custom-torsion-spring` — and **this module wins them**. That was measured,
not assumed: with both installed on the dev build, `/spring-calculator` came
back mounting `spring_calculator.calculator` instead of the original.

Everything else that would have collided is renamed — the Owl template, the
public component, the client action, the product XML IDs — so the clash is
one obvious thing rather than four subtle ones.

On this repository's own project, `spring_engineering` is the one that is
installed. This module lives here as the **source** for the second project
and is deliberately left uninstalled.


## Which Odoo versions it installs on

The manifest version is **`1.0.0`** — three parts, no series — and that is
deliberate. Odoo's loader refuses a module whose version does not start with
the running series, and it does so by greying out the Install button and
calling the module **"Uninstallable"** with no reason given anywhere on the
screen. A three-part version is prefixed with whatever series is running
(`1.0.0` becomes `19.0.1.0.0` on 19, `20.0.1.0.0` on 20), so the module is at
least offered.

## ⚠️ Odoo 19 only. It installs on Odoo 20 and does not run.

**Odoo 20 ships Owl 3**, which is a breaking rewrite of the UI framework, and
the calculator is a 4,449-line Owl 2 component. Checked against the Odoo 20
source on 2026-11-02 — the Odoo 20 *documentation* still shows `useState` and
is lagging; the source does not use it:

- `useState` (×4) — **removed in Owl 3**, replaced by `proxy`
- `t-esc` (×41) — **removed**, replaced by `t-out` (which also works in Owl 2)
- `useEffect` (×1) — signature changed, no second argument
- **`t-model` (×9) — now takes a SIGNAL**, not reactive state

That last one is why this is a migration and not a patch: those nine bindings
are the calculator's whole input surface, and moving off `useState` changes
how state is read in every one of those 4,449 lines. Owl 3 signals do not run
on Owl 2, so doing it would FORK the calculator permanently into a 19 version
and a 20 version — and this repository can only ever test the 19 one.

**So the second project was put on Odoo 19** (owner's call, 2026-11-02),
which is also what project 1 runs. Odoo.sh: the branch's **Settings → Odoo
version**.

Two things about Odoo 20 that were run down and **are** solved, should it ever
be revisited: the manifest version (see above), and `ir.config_parameter`
losing `get_param`/`set_param` in favour of typed accessors — `compat.py`
already bridges that one and is harmless on 19.

Three more that were checked and had **not** changed in 20:
`type="jsonrpc"` is still a valid route type;
`website._get_and_cache_current_cart()` and `._create_cart()` still exist;
`is_storable` is still a field on `product.template`.

Series before 19 are untested. `is_storable` does not exist before 18, and
`type="jsonrpc"` was `type="json"` before 19.

## Putting it on the second project

### The recommended way: a git submodule

One copy of the calculator in the world. A fix made here reaches both
projects.

1. Put `spring_calculator/` in a repository of its own.
2. In the second project's repo, add it as a submodule at the root (Odoo.sh
   fetches submodules at build time and puts them on the addons path).
3. For a private repository, Odoo.sh gives you a public deploy key — add it
   to the calculator repo's deploy keys so the build can clone it.
4. **Apps → Update Apps List**, search *Spring Calculator*, Install.

Step 4 is not optional and is easy to forget: merging a branch only updates
modules that are **already installed**. A module that did not exist before
sits in Apps waiting for somebody to install it, and nothing about a deploy
says so.

### The quicker way: copy the folder

Copy `spring_calculator/` into the second project's repo. Fine for a demo.
Not fine for two live sites — see *Keeping it in step* below for why.


## Keeping it in step

**151 of the 288 commits** to `spring_engineering` in the 90 days to
2026-11-02 touched the engine — `spring_engineering.js`,
`controllers/main.py`, `pricing.py` — the most recent five days before this
was written. This is not finished code you can fork and forget. A hand copy
is wrong within the fortnight, and wrong *silently*.

So after any change to the calculator in `spring_engineering`:

```bash
python3 tools/build_spring_calculator.py          # re-sync
python3 tools/build_spring_calculator.py --check  # exit 1 if stale
```

`--check` needs no database and no Odoo. **Run it before pushing** — it is
the cheapest guard there is.

The deeper proof is `spring_calculator/tests/`, which needs the module
installed:

```bash
odoo-bin -i spring_calculator --stop-after-init --no-http
odoo-bin --test-tags /spring_calculator --stop-after-init --no-http
# then uninstall it again, or it keeps the routes
```

`test_matches_the_original` runs the same eight specifications through **both**
engines and compares the quotes — price, description, turns, filler and the
refusals — and compares the 4,449-line browser engine as text after undoing
the renames. It skips itself where `spring_engineering` is absent, which is
the second project.


## What is in it

*(No markdown tables in this file: Odoo runs the README through docutils for
the Apps description, and a `|---|---|` separator logs an "Undefined
substitution" error on every install.)*

- `controllers/main.py` — the engine: constants, `quote_assembly`,
  `add_assembly_lines`, the routes
- `controllers/custom_spring.py` — the `/custom-torsion-spring` page
- `pricing.py` — steel rates, cone prices, the filler rate
- `static/src/js/spring_calculator.js` — the sizing maths, 4,449 lines,
  calibration baked in
- `models/sale_order_line.py` — `spring_spec_json`, `aa_spec_note`, the door
  figures
- `views/` — both pages, the two products, the backend app, the settings

## What is *not*

`spring_engineering` is eight features wearing one name. Only the first came
across:

- **catalogue merge** — 89 of *his* products, by name. Meaningless elsewhere.
- **track prep** — nearly all of `models/sale_order.py`
- **wishlist heart**, **signup validation**, **reorder**, **minimum order /
  quantity limits**, **cart cost line**, **shop grid price fix**

Which is why this module drops the `website_sale_wishlist` and `auth_signup`
dependencies: neither was ever any part of the calculator.

## Settings

**Website → Configuration → Settings → Spring Calculator**

- *Spring sell price per pound* — cost + winding labour + your margin. Not
  marked up again.
- *Spring steel cost per pound* — a **second figure**, not a division of the
  first. Nothing a customer sees is priced from it.

Both are stored under keys that still read `spring_engineering.*`. That is
deliberate: they are internal identifiers nobody looks at, and leaving them
alone is what lets `pricing.py` and the price-reading half of `main.py` copy
across completely untouched.

## Two things that travel with it

The calculator carries two business decisions, and they are decisions rather
than accidents:

- **Duplex is calculated but not sold.** The option stays, the pair is still
  worked out, the figures are still drawn — somebody sizing a duplex they
  already own is exactly who the page is for. The sale is refused in
  `UNBUILDABLE_ASSEMBLIES`. Turning it back on is deleting one word.
- **Only one Duplex I.D. and three Single I.D.s are calibrated.** Every one
  of the 8,464 reference readings behind the model is for `3 3/4" inside 6"`.
  **Do not add a size to the dropdown without calibrating it first** —
  offering a size the model cannot compute is worse than not offering it.
