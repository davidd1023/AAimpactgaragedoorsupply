"""PUT BACK THE MINIMUMS ODOO THREW AWAY.

Owner, 2026-10-29: *"some items dont have a minimum set even though you had
the information, for example cut down hinges says no minimum set when on the
excel it says the minimum is 288 for some of them."*

The rules were written by `sudo()` from the install hook, which made them
superuser-owned, and `manual` by deliberate choice. That is precisely the
shape Odoo's own `_unlink_processed_orderpoints` autovacuum deletes once
`qty_to_order` falls to nought - so **every part at or above its minimum lost
its rule, and only the short ones survived**. Cut Down Hinge is well stocked,
which is exactly why it was one of the casualties.

TWO STEPS, AND THE ORDER MATTERS:

1. **Repair what is left**, keeping the numbers it holds. A surviving rule may
   carry a minimum he has changed by hand since, and the fault was who owned
   the rule, not what it said.
2. **Re-load only what is MISSING**, so a deleted rule comes back from the
   file while nothing he has edited is written over.
"""

import logging

from odoo.addons.aa_min_max.models.minmax_load import load_levels, repair_doomed_rules

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})

    repaired = repair_doomed_rules(env)
    answer = load_levels(env, only_missing=True)

    _logger.info("aa_min_max: %s reordering rules re-owned; %s",
                 repaired, answer["params"]["message"])
