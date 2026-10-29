"""THE 36 MINIMUMS THE FIRST EXTRACTION THREW AWAY.

Owner, 2026-10-29: *"there are still some products missing, for example the
flag angles"* - and then the spreadsheet and a list of his Prod products.

His file holds **193 minimums, not the 157 that were shipped**. The 36
missing ones are exactly the rows with NO PART NUMBER, because the step that
turned his workbook into `minmax_levels.csv` required a Code and dropped
anything without one. All four flag angles were among them, along with
eighteen RAW track lengths, Cut Down Hinge #6-#9, Hinge #8-#9, the hollow
shaft and a drum.

That is not a rare shape: **84 of his 112 products carry no part number at
all**, and 161 of the 193 minimums can only be placed by name.

Rehearsed before this was written, against a 476-product reconstruction of
his catalogue built from his own export: 193 of 193 placed, none unmatched.

`only_missing=True`: the 36 are missing by definition, and a minimum he has
changed by hand since must not be written over by the file.
"""

import logging

from odoo.addons.aa_min_max.models.minmax_load import load_levels

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    answer = load_levels(env, only_missing=True)

    _logger.info("aa_min_max: the parts with no part number; %s",
                 answer["params"]["message"])
