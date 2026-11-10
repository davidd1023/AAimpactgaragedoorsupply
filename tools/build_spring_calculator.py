#!/usr/bin/env python3
"""Generate `spring_calculator` from `spring_engineering`.

WHY THIS IS A SCRIPT AND NOT A ONE-OFF COPY
===========================================

The owner wants the spring calculator on a second Odoo.sh project of his, and
NOTHING of `spring_engineering` may change to make that happen - his words,
2026-11-02: *"as long as it doesnt affect the original spring engineering
calculator in any way."*

So this does not carve the module up in place. It READS `spring_engineering`
and WRITES a second, lighter module beside it. The original is never opened
for writing, which is a promise a test can check (`git diff` on that folder
must be empty) rather than a promise somebody has to remember.

THE REASON IT IS GENERATED RATHER THAN COPIED BY HAND: **151 of the 288
commits** to `spring_engineering` in the 90 days to 2026-11-02 touched the
engine - `spring_engineering.js`, `controllers/main.py`, `pricing.py` - the
most recent five days before this was written. A hand copy of a file that
changes every other day is a copy that is wrong by the end of the fortnight,
and wrong silently, because nothing compares them. Re-running this script is
the whole of a re-sync, and `test_generated_module_is_current` fails the
build when somebody forgets.

This is the same arrangement as `tools/build_embed.py` and the door preview
block, for the same reason written down there: editing the generated thing by
hand is how the two come to differ, and then a fix made in one stays broken in
the other.

WHAT IS LEFT BEHIND, and it is most of the folder. `spring_engineering` is
eight features wearing one name; only the first is the calculator:

    the calculator ......... main.py, custom_spring.py, pricing.py, the JS
    catalogue merge ........ 89 of HIS products, by name - meaningless elsewhere
    track prep ............. nearly all of models/sale_order.py
    wishlist heart ......... controllers/wishlist.py + JS
    signup validation ...... controllers/signup.py
    reorder ................ controllers/reorder.py + 2 JS files
    minimum order / qty .... minimum_order.py, quantity_limits.js
    cart cost + grid price . cart_cost.py, shop_grid_price.py

THE TWO MODULES MUST NEVER BE INSTALLED IN THE SAME DATABASE. They claim the
same routes (`/spring-calculator`, `/custom-torsion-spring`). Everything else
that WOULD have collided is renamed below - the Owl template, the public
component, the client action tag, the product XML IDs - so the clash is one
thing and an obvious one, rather than four subtle ones.

Run it from anywhere:

    python3 tools/build_spring_calculator.py          # write
    python3 tools/build_spring_calculator.py --check  # exit 1 if stale
"""

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "spring_engineering"
DEST = ROOT / "spring_calculator"

#: Stamped into every generated file so nobody edits one by hand for twenty
#: minutes before noticing.
BANNER = (
    "GENERATED FROM spring_engineering BY tools/build_spring_calculator.py."
    " DO NOT EDIT BY HAND - change the original and re-run the script."
)

# ---------------------------------------------------------------------------
# THE RENAMES, IN ORDER. Order matters: `calculator_page` has to go before
# `calculator`, or the first six characters of the longer name are eaten and
# the page id comes out as `spring_calculator.calculator_page` only by luck.
#
# WHAT IS DELIBERATELY *NOT* RENAMED: the three `ir.config_parameter` keys
# (`spring_engineering.steel_per_lb`, `.steel_cost_per_lb`, `.markup_percent`).
# They are internal identifiers nobody reads - the owner sees "Spring sell
# price per pound" in Settings - and leaving them alone means two things:
# `pricing.py` and the price-reading half of `main.py` copy across completely
# untouched, and if the two modules ever did share a database they would agree
# on the steel rate rather than quietly quoting from two different ones.
# ---------------------------------------------------------------------------
RENAMES = [
    ("spring_engineering.product_custom_spring", "spring_calculator.product_custom_spring"),
    ("spring_engineering.product_custom_filler", "spring_calculator.product_custom_filler"),
    ("spring_engineering.custom_torsion_spring_page", "spring_calculator.custom_torsion_spring_page"),
    ("spring_engineering.calculator_page", "spring_calculator.calculator_page"),
    ("spring_engineering.Calculator", "spring_calculator.Calculator"),
    ("spring_engineering.calculator", "spring_calculator.calculator"),
    # ODOO 20 DROPPED `get_param`. It replaced ir.config_parameter's generic
    # get_param/set_param with TYPED accessors - get_str, get_float, get_int,
    # get_bool and their setters - and the module died on install with
    # `'ir.config_parameter' object has no attribute 'get_param'` (owner,
    # 2026-11-02, on his Odoo 20 project).
    #
    # `compat.py` below keeps ONE file set working on 19 and 20 alike, which
    # matters because the equivalence tests that prove this carve correct can
    # only run here, on 19. Two anchors, both verified unique to main.py:
    # the relative import (custom_spring.py's pricing import has no bracket)
    # and the one call itself.
    ("from ..pricing import (",
     "from ..compat import config_rate\nfrom ..pricing import ("),
    ('request.env["ir.config_parameter"].sudo().get_param(key)',
     "config_rate(request.env, key)"),

    # ---- OWL 2 **OR** OWL 3, FROM ONE FILE SET -----------------------------
    #
    # Odoo 20 ships OWL 3, which is a breaking rewrite: `useState` is gone in
    # favour of `proxy`, `t-esc` is gone in favour of `t-out`, and `useEffect`
    # no longer takes a dependencies argument. Odoo 19 ships Owl 2, which is
    # where this repository's tests run - so neither version may be abandoned.
    #
    # BOTH OF THESE WORK ON OWL 2 TOO, which is the whole point: they can be
    # proved here not to break anything, rather than written blind. `t-out`
    # has existed since Owl 2 and escapes plain strings exactly as `t-esc`
    # did; the hooks are chosen at runtime off a feature test.
    #
    # STILL OUTSTANDING: the nine `t-model` bindings, which in Owl 3 take a
    # SIGNAL. Seven of them are on `<select>`, where the obvious replacement
    # (`t-att-value`) does not select an option, and the right answer cannot
    # be checked from a container that only has Owl 2. See the README.
    ("t-esc=\"", "t-out=\""),
    ('import { Component, onWillStart, useEffect, useState } from "@odoo/owl";',
     'import * as owl from "@odoo/owl";'),
    # The hooks are resolved AFTER the imports rather than in place of them:
    # `import` is hoisted so either is legal, but a const block sitting above
    # the remaining imports reads like a mistake and invites somebody to
    # "fix" it.
    ('import { _t } from "@web/core/l10n/translation";',
     'import { _t } from "@web/core/l10n/translation";\n'
     '\n'
     '// OWL 2 OR OWL 3 - see tools/build_spring_calculator.py. Odoo 19 has\n'
     '// Owl 2 and `useState`; Odoo 20 has Owl 3, where it is `proxy` and\n'
     '// `useEffect` takes no dependencies argument.\n'
     'const { Component, onWillStart } = owl;\n'
     'const OWL2 = typeof owl.useState === "function";\n'
     'const useState = OWL2 ? owl.useState : owl.proxy;\n'
     'const useEffect = OWL2 ? owl.useEffect : (effect) => owl.useEffect(effect);'),

    # The backend app: its menu and action ids, and the words on the menu.
    ("action_spring_engineering", "action_spring_calculator"),
    ("menu_spring_engineering", "menu_spring_calculator"),
    (">Spring Engineering<", ">Spring Calculator<"),
    ('name="Spring Engineering"', 'name="Spring Calculator"'),
    ('web_icon="spring_engineering,', 'web_icon="spring_calculator,'),
    # The prefix on log lines, so a support question about the second project
    # does not send somebody reading the first one's code.
    ('"spring_engineering: ', '"spring_calculator: '),
    # NOT RENAMED, deliberately: the `/spring_engineering` and
    # `/spring-engineering` entries in ALIASES. They 301 to the canonical
    # page and cost nothing, and leaving them keeps main.py a verbatim copy
    # of the original but for the names above.
    #
    # File paths named in comments, so the comments stay true after the rename.
    ("spring_engineering_site.css", "spring_calculator_site.css"),
    ("spring_engineering.js", "spring_calculator.js"),
    ("spring_engineering.xml", "spring_calculator.xml"),
    ("spring_engineering.css", "spring_calculator.css"),
]

#: Copied whole, with the renames applied. These are the engine.
COPY = [
    ("pricing.py", "pricing.py"),
    ("controllers/main.py", "controllers/main.py"),
    ("controllers/custom_spring.py", "controllers/custom_spring.py"),
    ("views/spring_engineering_product.xml", "views/spring_calculator_product.xml"),
    ("views/spring_engineering_templates.xml", "views/spring_calculator_templates.xml"),
    ("views/custom_torsion_spring_templates.xml", "views/custom_torsion_spring_templates.xml"),
    ("views/spring_engineering_views.xml", "views/spring_calculator_views.xml"),
    ("static/src/js/spring_engineering.js", "static/src/js/spring_calculator.js"),
    ("static/src/xml/spring_engineering.xml", "static/src/xml/spring_calculator.xml"),
    ("static/src/css/spring_engineering.css", "static/src/css/spring_calculator.css"),
    ("static/src/css/spring_engineering_site.css", "static/src/css/spring_calculator_site.css"),
]

#: Taken from a marker to the end of the file. `sale_order_line.py` holds the
#: spring fields AND the track-prep ones; only the spring half travels, and it
#: happens to be the tail of the file.
SLICE = [
    (
        "models/sale_order_line.py",
        "models/sale_order_line.py",
        "    # THE SPRING AS DATA (JSON)",
        'from odoo import api, fields, models\n'
        '\n'
        '\n'
        'class SaleOrderLine(models.Model):\n'
        '    _inherit = "sale.order.line"\n'
        '\n',
    ),
]


def comment(text, style):
    """The banner, in whichever language the file is written in."""
    if style == "py":
        return f"# {text}\n"
    if style == "js":
        return f"// {text}\n"
    if style == "css":
        return f"/* {text} */\n"
    return ""


def style_for(path):
    suffix = pathlib.Path(path).suffix
    return {".py": "py", ".js": "js", ".css": "css", ".xml": "xml"}.get(suffix, "")


def apply_renames(text):
    for old, new in RENAMES:
        text = text.replace(old, new)
    return text


def xml_banner(text):
    """XML cannot take a comment before its declaration, so it goes after."""
    lines = text.split("\n", 1)
    if lines[0].startswith("<?xml"):
        return f"{lines[0]}\n<!-- {BANNER} -->\n{lines[1] if len(lines) > 1 else ''}"
    return f"<!-- {BANNER} -->\n{text}"


def build():
    """Every generated file, as {relative path: content}."""
    out = {}

    for src, dest in COPY:
        text = apply_renames((SRC / src).read_text())
        style = style_for(dest)

        if style == "xml":
            text = xml_banner(text)
        elif style:
            text = comment(BANNER, style) + text

        out[dest] = text

    for src, dest, marker, header in SLICE:
        text = (SRC / src).read_text()
        at = text.find(marker)

        if at == -1:
            raise SystemExit(
                f"{src}: marker not found - {marker!r}.\n"
                "The original was restructured. Find the spring fields and "
                "update SLICE; do not edit the generated file."
            )

        out[dest] = comment(BANNER, "py") + apply_renames(header + text[at:])

    out.update(handwritten())

    return out


def handwritten():
    """The files with no counterpart in the original.

    Short, and they change when the MODULE's shape changes rather than when
    the engine does - which is the thing that moves. Kept here so there is
    still exactly one place the generated module is described.
    """
    files = {}

    files["__manifest__.py"] = f'''# {BANNER}
{{
    "name": "Spring Calculator",
    # NO SERIES IN THE VERSION, ON PURPOSE (owner, 2026-11-02: his second
    # project turned out to run Odoo 20, and the module showed up in Apps as
    # "Uninstallable" with no reason given).
    #
    # Odoo's loader does this, in odoo/modules/module.py:
    #
    #     if manifest['installable'] and not check_version(version, ...):
    #         manifest['installable'] = False
    #
    # and `check_version` passes only when the version STARTS WITH the
    # running series. A five-part "19.0.1.0.0" is returned unchanged by
    # `adapt_version`, so it fails on 20.0 - silently, as a greyed-out
    # button. A THREE-part version is PREFIXED with whatever series is
    # running ("1.0.0" -> "20.0.1.0.0"), so the module is offered on any of
    # them.
    #
    # THE TRADE, WRITTEN DOWN: Odoo will no longer refuse this module on a
    # series it was not written for. That refusal was worth something - but
    # not much, since it names no reason - and it is worth less than being
    # able to install the thing and read a real traceback.
    "version": "1.0.0",
    "category": "Engineering",
    "summary": "Torsion spring calculator, quote and cart",
    "author": "AA Impact Garage Door Supply",
    "license": "LGPL-3",
    # ONLY WHAT THE CALCULATOR ITSELF NEEDS. The original also pulls in
    # `website_sale_wishlist` (for the heart toggle) and `auth_signup` (for
    # the address check); neither is any part of the calculator, and both are
    # left behind with the features that wanted them.
    "depends": ["sale_management", "website", "website_sale"],
    "data": [
        "views/spring_calculator_settings.xml",
        "views/spring_calculator_product.xml",
        "views/spring_calculator_templates.xml",
        "views/custom_torsion_spring_templates.xml",
        "views/spring_calculator_views.xml",
        "views/spring_calculator_config_settings.xml",
    ],
    # THE SAME THREE FILES IN BOTH BUNDLES, as in the original: the backend
    # action and the public page mount one component from one source.
    "assets": {{
        "web.assets_backend": [
            "spring_calculator/static/src/js/spring_calculator.js",
            "spring_calculator/static/src/xml/spring_calculator.xml",
            "spring_calculator/static/src/css/spring_calculator.css",
        ],
        "web.assets_frontend": [
            "spring_calculator/static/src/js/spring_calculator.js",
            "spring_calculator/static/src/xml/spring_calculator.xml",
            "spring_calculator/static/src/css/spring_calculator.css",
            "spring_calculator/static/src/css/spring_calculator_site.css",
        ],
    }},
    "installable": True,
    "application": True,
    # IT WILL NOT INSTALL BESIDE THE ORIGINAL, AND THAT IS THE WHOLE POINT
    # (owner, 2026-11-10: *"can you make it so that the spring calculator
    # thing cant be added to apps"*). See `_refuse_beside_the_original`.
    "pre_init_hook": "_refuse_beside_the_original",
}}
'''

    # WHY A HOOK AND NOT `installable: False`.
    #
    # The danger is ONE DATABASE WITH BOTH MODULES: they claim the same two
    # routes and this one WINS them, which was measured rather than assumed -
    # with both installed here, /spring-calculator came back mounting
    # `spring_calculator.calculator` instead of the original. On his live site
    # that is the calculator page replaced by a copy carrying none of his
    # products.
    #
    # `installable: False` would stop that and ALSO stop the second project,
    # which is the only reason this module exists - and the second project
    # copies this folder, so the flag travels with it. A blanket ban is the
    # wrong shape for a rule that is really about sharing a database.
    #
    # So the refusal is exactly the collision: `spring_engineering` present in
    # THIS database. On the second project that module does not exist and the
    # install proceeds untouched.
    #
    # `pre_init_hook` RUNS ONLY ON INSTALL (odoo/modules/loading.py checks
    # `update_operation == 'install'`) and before the models load, so an
    # existing install still updates normally and nothing half-installs.
    # Read off the Odoo 19 source, not guessed: it is called as `hook(env)`.
    #
    # It is a refusal with a REASON ON THE SCREEN, which is worth more than a
    # module missing from the list - the last time something was hidden from
    # Apps (`aa_min_max`, `application: False`) the one person who needed it
    # could not find it, and nothing said why.
    files["__init__.py"] = f'''# {BANNER}
from odoo.exceptions import UserError

from . import controllers
from . import models


def _refuse_beside_the_original(env):
    """Refuse to install where `spring_engineering` already lives.

    Both modules claim /spring-calculator and /custom-torsion-spring, and
    this one wins them - so installing it on the database that runs the shop
    would silently replace the live calculator with a copy that has none of
    the shop's products behind it.
    """
    original = env["ir.module.module"].sudo().search(
        [("name", "=", "spring_engineering"),
         ("state", "in", ("installed", "to upgrade", "to install"))], limit=1)

    if original:
        raise UserError(
            "Spring Calculator cannot be installed on this database.\\n\\n"
            "The Spring Engineering module is already installed here, and the"
            " two claim the same pages (/spring-calculator and"
            " /custom-torsion-spring). This one would take them over, so the"
            " calculator would stop showing the shop's own products.\\n\\n"
            "This module is the copy kept for the separate calculator-only"
            " project. Nothing needs to be installed here."
        )
'''
    files["controllers/__init__.py"] = (
        f"# {BANNER}\nfrom . import main\nfrom . import custom_spring\n"
    )
    files["models/__init__.py"] = (
        f"# {BANNER}\nfrom . import ir_config_parameter\n"
        "from . import res_config_settings\nfrom . import sale_order_line\n"
    )

    files["compat.py"] = f'''# {BANNER}
"""ONE FILE SET, TWO ODOO SERIES.

**Odoo 20 removed `ir.config_parameter.get_param` and `set_param`** and put
typed accessors in their place - `get_str`, `get_float`, `get_int`,
`get_bool` and matching setters. The module died on install with

    AttributeError: 'ir.config_parameter' object has no attribute 'get_param'

WHY A SHIM RATHER THAN JUST MOVING TO THE NEW API: the tests that prove this
carve correct - the ones that run eight specifications through BOTH engines
and compare the quotes - can only run where `spring_engineering` is, which is
Odoo 19. A module that only installs on 20 is a module whose maths nothing
checks.

**READ IT THE WAY IT IS WRITTEN.** Both parameters back `Float` fields on
res.config.settings, and on Odoo 20 Odoo's own settings page writes them with
`set_float`. Reading a float row back with `get_str` returns INVALID_VALUE,
which `get_str` turns into the default - indistinguishable from a deleted
parameter, which the engine turns into "call us". So these use the FLOAT
accessors on 20, matching what the settings page does.
"""


def config_rate(env, key):
    """The stored rate, or None/False when there is no row.

    The caller tells a missing parameter from a zero and refuses to quote on
    the first - which is the whole point of it, so neither series may answer
    "0.0" for "absent".
    """
    params = env["ir.config_parameter"].sudo()

    if hasattr(params, "get_float"):        # Odoo 20 and later
        return params.get_float(key, None)

    return params.get_param(key)            # Odoo 19 and earlier


def set_config_rate(env, key, value):
    """Store a rate so that ZERO survives.

    On Odoo 19 `set_param` DELETES the row when handed a falsy value, so the
    figure goes in as a string - a deliberate 0 would otherwise read back as
    a deleted parameter and turn every quote into "call us". Odoo 20 does not
    have that fault (`0.0 is False` is False, so the float is stored), and
    takes the float.
    """
    params = env["ir.config_parameter"].sudo()

    if hasattr(params, "set_float"):        # Odoo 20 and later
        params.set_float(key, float(value))
    else:
        params.set_param(key, str(value))   # Odoo 19 and earlier
'''

    files["models/ir_config_parameter.py"] = f'''# {BANNER}
from odoo import api, models

from ..compat import config_rate, set_config_rate
from ..pricing import STEEL_COST_PER_LB, STEEL_PRICE_PER_LB

# THE KEYS KEEP THE `spring_engineering.` PREFIX ON PURPOSE - see the note in
# tools/build_spring_calculator.py. They are internal identifiers nobody
# reads, and leaving them alone is what lets pricing.py and main.py copy
# across untouched.
#
# `markup_percent` is NOT shipped. _markup_factor() has returned 1 since
# 2026-10-16 ("cones and filler at cost, markup setting removed"), so the row
# would be a default for a figure nothing reads.
DEFAULTS = {{
    "spring_engineering.steel_per_lb": STEEL_PRICE_PER_LB,
    "spring_engineering.steel_cost_per_lb": STEEL_COST_PER_LB,
}}


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def _spring_calculator_ensure_defaults(self):
        """Create the pricing parameters if absent. Never overwrite.

        A FUNCTION RATHER THAN `noupdate` RECORDS, which is the original's
        hard-won shape and is kept: set_param DELETES the row when handed a
        falsy value, taking the xmlid with it, and the next module update then
        tries to INSERT a record whose key already exists - which fails the
        whole registry. Addressing the parameter by key cannot collide.

        A STORED "0" IS A VALUE and is left alone; only a missing or blank
        parameter is filled in.
        """
        for key, default in DEFAULTS.items():
            if config_rate(self.env, key) in (None, False, ""):
                set_config_rate(self.env, key, default)
'''

    files["models/res_config_settings.py"] = f'''# {BANNER}
from odoo import fields, models

from ..compat import set_config_rate


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def set_values(self):
        """Write the rates so that ZERO survives the trip.

        Odoo stores a `config_parameter` field by handing its value to
        set_param, and a falsy value there does not store a zero - it DELETES
        the row. The reader in controllers/main.py refuses to quote when a
        parameter is missing, on purpose, so a deliberate 0 typed into this
        form would otherwise turn every quote into "call us". Writing the
        figures explicitly as strings keeps both halves.
        """
        super().set_values()

        set_config_rate(self.env, "spring_engineering.steel_per_lb",
                        self.spring_steel_per_lb or 0.0)
        set_config_rate(self.env, "spring_engineering.steel_cost_per_lb",
                        self.spring_steel_cost_per_lb or 0.0)

    # THE SELL RATE: cost + winding labour + margin, per pound. It is NOT
    # marked up again - see pricing.py.
    spring_steel_per_lb = fields.Float(
        string="Spring sell price per pound",
        config_parameter="spring_engineering.steel_per_lb",
    )
    # A SECOND FIGURE, not a division of the first: no arithmetic on a sell
    # rate with labour inside it can recover a cost. Nothing a customer sees
    # is priced from this.
    spring_steel_cost_per_lb = fields.Float(
        string="Spring steel cost per pound",
        config_parameter="spring_engineering.steel_cost_per_lb",
    )
'''

    files["views/spring_calculator_settings.xml"] = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- {BANNER} -->
<odoo>

    <!-- THE RATES, SHIPPED AS A CALL RATHER THAN AS RECORDS. A
         <record noupdate="1"> loses its xmlid the first time somebody sets
         the value to zero (set_param deletes the row), and the next module
         update collides on the key and takes the registry down with it. That
         is not theoretical - it happened on the original. A function
         addresses the parameter by key, which is its real identity. -->
    <function model="ir.config_parameter" name="_spring_calculator_ensure_defaults"/>

</odoo>
'''

    files["views/spring_calculator_config_settings.xml"] = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- {BANNER} -->
<odoo>

    <record id="res_config_settings_view_form" model="ir.ui.view">
        <field name="name">res.config.settings.view.form.inherit.spring.calculator</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="website.res_config_settings_view_form"/>
        <field name="arch" type="xml">
            <!-- The rates live in Website's settings because the calculator
                 is a website page, anchored after the Website app's own
                 General block - the same anchor the original uses, and it
                 has to be a real one: an xpath that matches nothing fails
                 the whole install, which is how the first build of this
                 module died. -->
            <xpath expr="//block[@id='website_info_settings']" position="after">
                <block title="Spring Calculator" id="spring_calculator_settings">
                    <setting string="Spring sell price per pound"
                             help="What a pound of wound spring steel SELLS for: your cost, the winding labour and your margin. It is not marked up again.">
                        <div class="content-group">
                            <div class="row">
                                <field name="spring_steel_per_lb" class="oe_inline"/>
                                <span class="ms-2">per lb</span>
                            </div>
                        </div>
                    </setting>
                    <setting string="Spring steel cost per pound"
                             help="What the steel COSTS you. Nothing a customer sees is priced from this - it is used for staff-only cost figures.">
                        <div class="content-group">
                            <div class="row">
                                <field name="spring_steel_cost_per_lb" class="oe_inline"/>
                                <span class="ms-2">per lb</span>
                            </div>
                        </div>
                    </setting>
                </block>
            </xpath>
        </field>
    </record>

</odoo>
'''

    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed module is out of date")
    args = parser.parse_args()

    files = build()
    stale = []

    for rel, content in sorted(files.items()):
        path = DEST / rel

        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(rel)
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    # A file DELETED from the generated module is drift too - it would sit
    # there being loaded by the manifest long after its source went away.
    expected = {str(p) for p in files}
    for path in DEST.rglob("*"):
        rel = str(path.relative_to(DEST))
        # `static/description/` is the Apps-card icon, which is an ASSET and
        # not generated content - the original ships none, so there is
        # nothing to copy. Without it the Apps screen falls back to Odoo's
        # generic grey cube while the home-screen tile shows the shop's red
        # one, which is the two screens disagreeing about the same module.
        if path.is_file() and rel not in expected and not rel.startswith(
                ("tests/", "README", "__pycache__", "static/description/")):
            stale.append(f"{rel} (not generated by this script)")

    if args.check:
        if stale:
            print("spring_calculator is OUT OF DATE:", file=sys.stderr)
            for rel in sorted(stale):
                print(f"  {rel}", file=sys.stderr)
            print("\nRun: python3 tools/build_spring_calculator.py", file=sys.stderr)
            return 1
        print(f"spring_calculator is current ({len(files)} files).")
        return 0

    print(f"Wrote {len(files)} files to {DEST}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
