"""RECORD WHAT THE FILE SAID, so the screen can answer "why not".

Owner, 2026-10-29: *"there are still some products missing, for example the
flag angles."* They were never in the file - and the screen said "No Minimum
Set", the same words it used for the ones Odoo had deleted. Two completely
different problems, one sentence, and no way for him to tell them apart.

This re-reads the file so every row becomes a record with its result, which
is what the new "Why No Minimum" column reads.

`only_missing=True`, as in the repair before it: a minimum he has changed by
hand since must not be written over by the file.
"""

import logging

from odoo.addons.aa_min_max.models.minmax_load import load_levels

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    answer = load_levels(env, only_missing=True)

    _logger.info("aa_min_max: file rows recorded; %s",
                 answer["params"]["message"])
