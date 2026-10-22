"""FOLD THE CATALOGUE'S COLOURS, SIZES AND HANDS INTO ONE PRODUCT PER PART.

Runs once, when the database reaches 19.0.2.49.0. What it does and why is in
models/product_variant_merge.py; what it does it TO is models/variant_families.

IT REHEARSES FIRST, EVERY TIME. The rehearsal performs all fifteen families
and rolls them back, and both reports go into the log - so the log says what
was about to happen and then what did, and the two can be read against each
other. On a staging build that is the whole review: read the rehearsal, and if
a family is listed as skipped, the line underneath says which product it could
not account for.

A FAMILY THAT DOES NOT ADD UP IS LEFT ALONE, not forced. A product missing
from the catalogue, two colours of one size disagreeing about the price, stock
still reserved on a delivery that has not gone out - each of those skips its
own family and says so in the log, and the other fourteen go ahead. Nothing is
deleted either way: the products that are folded in are archived, and their
stock is moved by inventory adjustment, so every count leaves a move behind
saying where it went.

HOW TO STOP IT, from the Odoo interface and without a developer: set the
system parameter `spring_engineering.variant_merge_hold` to 1 (Settings >
Technical > System Parameters) before the build. It will rehearse, log, and
change nothing. That is there because a migration runs on Prod the moment the
owner merges, and he should not need us to call it off.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

HOLD = "spring_engineering.variant_merge_hold"


def migrate(cr, version):
    if not version:
        return  # a fresh database has no catalogue to fold

    env = api.Environment(cr, SUPERUSER_ID, {})
    Template = env["product.template"]

    # THE REHEARSAL. Performed and rolled back, so what it reports is what
    # happened rather than what somebody expected to happen.
    rehearsal = Template._aa_merge_variant_families(dry_run=True)

    held = (env["ir.config_parameter"].get_param(HOLD) or "").strip()
    if held and held.lower() not in ("0", "false", "no"):
        _logger.warning(
            "Variant merge HELD by %s - rehearsed only, catalogue unchanged.\n%s",
            HOLD, Template._aa_merge_report(rehearsal),
        )
        return

    merged = Template._aa_merge_variant_families(dry_run=False)

    # SAID TWICE, LOUDLY, because this is the line somebody will come looking
    # for weeks later when a count looks wrong.
    skipped = [r["survivor"] for r in merged if r["state"] == "skipped"]
    _logger.log(
        logging.WARNING if skipped else logging.INFO,
        "Variant merge done. %d of %d families merged%s\n%s",
        sum(1 for r in merged if r["state"] in ("merged", "already merged")),
        len(merged),
        (", LEFT ALONE: %s" % ", ".join(skipped)) if skipped else "",
        Template._aa_merge_report(merged),
    )
