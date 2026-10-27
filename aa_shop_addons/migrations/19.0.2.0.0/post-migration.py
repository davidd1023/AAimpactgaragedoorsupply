"""COUNT IT ONCE ON THE WAY IN, so the pages are right before tonight.

The cron rebuilds this every night, which means that without this the website
would spend its first day after the deploy still showing the families and he
would reasonably conclude nothing had happened.

A failure here must not take the deploy down with it: the recommendations are
an improvement on a page that already works, and the cron will try again in a
few hours.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    try:
        env["aa.addon.suggestion"]._aa_rebuild()
    except Exception:       # noqa: BLE001 - never fail a deploy over this
        _logger.exception(
            "aa_shop_addons: the first count of add-ons sold together failed;"
            " the nightly job will try again")
