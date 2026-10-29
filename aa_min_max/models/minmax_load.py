"""LOADING THE 157 MINIMUMS HE FILLED IN.

The spreadsheet came back with a Min against 157 parts and blank against 98 -
his own rule, written on its "How to fill" tab: *"Leave Min and Max blank for
parts you don't want to track."* So a blank is loaded as nothing at all, never
as nought.

**A PART NUMBER NO LONGER IDENTIFIES A PART.** Since the catalogue merge of
2026-10-21 one part number belongs to a whole family: `CH1108` is all EIGHT
jamb brackets, `CH1119D` all four spring anchor brackets, `CH1411-1` three
colours of the same hinge. THIRTY-TWO of the codes in his file are shared like
that. Matching on the code alone would have put one bracket's minimum on
eight, and - worse - would have looked like it worked.

So the match is **code first, then the variant's own name**, and the name in
his file is the one Odoo prints: `Jamb Bracket (Black, #10)`. Compared with
punctuation and case flattened, because a straight quote and a typographic one
are the same bracket.

**NOTHING IS GUESSED.** A row matching no product, or still matching several
after the name, is REPORTED and not loaded. A minimum silently attached to the
wrong variant is worse than one that was never loaded: the screen would say a
part is fine while the rack is empty.

**THE RULES ARE WRITTEN AS `manual`.** An `auto` reordering rule is picked up
by Odoo's scheduler, which raises purchase orders by itself - and 97 of these
parts are already below their minimum, so installing this with `auto` would
have sent a wall of orders to four suppliers the same night. Manual rules show
in Replenishment with an Order button and wait to be told.
"""

import csv
import logging
import os
import re

from odoo import _

_logger = logging.getLogger(__name__)

#: The file he filled in, turned into a column of numbers.
LEVELS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "data", "minmax_levels.csv")

#: Set once the file has been loaded, so installing does not undo his edits.
LOADED_FLAG = "aa_min_max.levels_loaded"


def flatten(text):
    """A name with its punctuation and case taken out.

    `Torsion Spring Coil 2 5/8" I.D. x 84" (.243, L)` and the same line with a
    typographic quote are the same coil, and a file that has been round a
    spreadsheet and back cannot be trusted to have kept either.
    """
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def read_levels():
    """[(code, name, min, max, vendor)] out of the shipped file."""
    rows = []

    with open(LEVELS_FILE, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not (row.get("code") or "").strip():
                continue

            def number(key):
                value = (row.get(key) or "").strip()

                try:
                    return float(value)
                except ValueError:
                    return 0.0

            rows.append({
                "code": row["code"].strip(),
                "name": (row.get("name") or "").strip(),
                "min_qty": number("min_qty"),
                "max_qty": number("max_qty"),
                "vendor": (row.get("vendor") or "").strip(),
            })

    return rows


def _match(env, row, by_code):
    """(product, why it could not be matched)."""
    candidates = by_code.get(row["code"])

    if not candidates:
        return None, _("no part has the number %s", row["code"])

    if len(candidates) == 1:
        return candidates[0], None

    # SEVERAL VARIANTS SHARE THIS NUMBER - the catalogue merge. The name is
    # the only thing left that tells them apart.
    #
    # THREE TIERS, STRICTEST FIRST, because a loose match here is how "#1"
    # swallows "#10". `Hinge (Black, #1)` flattens to `hingeblack1`, which is
    # a substring of `Hinge (Black, #10)` - so a plain substring test would
    # put the #1 minimum on the #10 bracket, or (better but still wrong)
    # refuse a row it could have placed exactly. His hinges stop at #9 and his
    # jamb brackets start at #10, so today nothing collides; the day a #10
    # hinge is stocked, this still lands on the right one.
    wanted = flatten(row["name"])
    tiers = (
        # The name with the part-number prefix taken off - what Odoo prints.
        [p for p in candidates
         if flatten(p.display_name) == flatten("[%s] %s" % (p.default_code, row["name"]))],
        [p for p in candidates if flatten(p.display_name).endswith(wanted)],
        [p for p in candidates if wanted in flatten(p.display_name)],
    )

    for named in tiers:
        if len(named) == 1:
            return named[0], None

    named = tiers[-1]

    if not named:
        return None, _("%s has %d variants and none is named %r",
                       row["code"], len(candidates), row["name"])

    return None, _("%s matches %d variants named like %r",
                   row["code"], len(named), row["name"])


def load_levels(env, set_vendors=True, rows=None):
    """Write his minimums onto Odoo's reordering rules. Re-runnable.

    Returns a notification describing what happened - loaded, left alone, and
    every row it refused, because a loader that says "done" while skipping
    forty rows is how a shop runs out of something the screen called fine.
    """
    # `rows` is for the tests, which need his exact shapes - a shared part
    # number, an ambiguous name - without shipping fixtures in the data file.
    rows = read_levels() if rows is None else rows
    Product = env["product.product"].sudo()
    Orderpoint = env["stock.warehouse.orderpoint"].sudo()
    warehouse = env["stock.warehouse"].search(
        [("company_id", "=", env.company.id)], limit=1)

    if not warehouse:
        return _notify(env, _("There is no warehouse to set levels in."), "danger")

    # One search for every code in the file, rather than 157 searches.
    products = Product.search([("default_code", "in", [r["code"] for r in rows])])
    by_code = {}

    for product in products:
        by_code.setdefault(product.default_code, []).append(product)

    written, unchanged, refused = 0, 0, []

    for row in rows:
        product, why = _match(env, row, by_code)

        if not product:
            refused.append(why)
            continue

        orderpoint = Orderpoint.search(
            [("product_id", "=", product.id),
             ("warehouse_id", "=", warehouse.id)], limit=1)
        # ODOO REFUSES A MAXIMUM BELOW THE MINIMUM - "The minimum quantity
        # must be less than or equal to the maximum quantity" - and he left
        # EVERY maximum blank ("we can just worry about the minimum for now").
        # So a blank maximum is stored AS the minimum, which in Odoo's own
        # terms means "order just enough to get back to the minimum". That is
        # the conservative reading of a blank, it keeps the warning exactly
        # right, and it is replaced the moment he types a real maximum.
        #
        # The screen does NOT then show a maximum: it blanks one equal to the
        # minimum, so the column stays empty exactly where he left it empty
        # rather than filling 157 rows with a figure he never chose.
        values = {"product_min_qty": row["min_qty"],
                  "product_max_qty": row["max_qty"] or row["min_qty"]}

        if orderpoint:
            if all(abs(orderpoint[key] - value) < 1e-6
                   for key, value in values.items()):
                unchanged += 1
            else:
                orderpoint.write(values)
                written += 1
        else:
            Orderpoint.create(dict(
                values,
                product_id=product.id,
                warehouse_id=warehouse.id,
                location_id=warehouse.lot_stock_id.id,
                # NEVER `auto` - see this module's docstring.
                trigger="manual",
            ))
            written += 1

        if set_vendors and row["vendor"]:
            _ensure_vendor(env, product, row["vendor"])

    message = _("%(written)s levels set, %(unchanged)s already right.",
                written=written, unchanged=unchanged)

    if refused:
        # NAMED, NOT COUNTED. "12 rows skipped" is not something anybody can
        # act on; the first few names are.
        message += _(" %(count)s could not be matched: %(detail)s",
                     count=len(refused), detail="; ".join(refused[:5]))
        # TRUNCATED. The first install here refused all 157 rows and wrote
        # every one of them onto a single log line, which is a paragraph
        # nobody reads where a count and a sample is read at a glance.
        _logger.warning("aa_min_max: %s of %s rows unmatched, e.g. %s",
                        len(refused), len(rows), "; ".join(refused[:10]))

    return _notify(env, message, "warning" if refused else "success")


def _ensure_vendor(env, product, name):
    """Put his sheet's vendor on the part, if the part has none.

    HE ALREADY TOLD ME WHO SELLS EACH PART - a column of his spreadsheet -
    and Odoo cannot raise a purchase order without it. Leaving it on the floor
    would mean asking him for the same thing again the day he wants the
    reorder automated.

    IT NEVER OVERWRITES. A part that already names a vendor is left exactly as
    it is: that is purchasing's own data, with prices and lead times behind
    it, and a spreadsheet column is not grounds for touching it.
    """
    if product.seller_ids:
        return

    partner = env["res.partner"].sudo().search(
        [("name", "=", name)], limit=1)

    if not partner:
        partner = env["res.partner"].sudo().create({"name": name,
                                                    "supplier_rank": 1})

    env["product.supplierinfo"].sudo().create({
        "partner_id": partner.id,
        "product_tmpl_id": product.product_tmpl_id.id,
    })


def load_levels_once(env):
    """The first install loads his numbers; later updates leave them alone."""
    params = env["ir.config_parameter"].sudo()

    if params.get_param(LOADED_FLAG):
        return

    load_levels(env)
    params.set_param(LOADED_FLAG, "1")


def _notify(env, message, kind):
    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {"title": _("Min / Max Levels"), "message": message,
                   "type": kind, "sticky": True, "next": {"type": "ir.actions.act_window_close"}},
    }
