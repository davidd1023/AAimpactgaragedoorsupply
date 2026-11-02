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
    "version": "19.0.1.0.0",
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
}}
'''

    files["__init__.py"] = f"# {BANNER}\nfrom . import controllers\nfrom . import models\n"
    files["controllers/__init__.py"] = (
        f"# {BANNER}\nfrom . import main\nfrom . import custom_spring\n"
    )
    files["models/__init__.py"] = (
        f"# {BANNER}\nfrom . import ir_config_parameter\n"
        "from . import res_config_settings\nfrom . import sale_order_line\n"
    )

    files["models/ir_config_parameter.py"] = f'''# {BANNER}
from odoo import api, models

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
    "spring_engineering.steel_per_lb": str(STEEL_PRICE_PER_LB),
    "spring_engineering.steel_cost_per_lb": str(STEEL_COST_PER_LB),
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
        params = self.sudo()

        for key, default in DEFAULTS.items():
            if not (params.get_param(key) or "").strip():
                params.set_param(key, default)
'''

    files["models/res_config_settings.py"] = f'''# {BANNER}
from odoo import fields, models


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

        params = self.env["ir.config_parameter"].sudo()
        params.set_param(
            "spring_engineering.steel_per_lb", str(self.spring_steel_per_lb or 0.0)
        )
        params.set_param(
            "spring_engineering.steel_cost_per_lb",
            str(self.spring_steel_cost_per_lb or 0.0),
        )

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
        if path.is_file() and rel not in expected and not rel.startswith(
                ("tests/", "README", "__pycache__")):
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
