"""Spanish for the Shop Floor (owner, 2026-11-11).

Switch Latin American Spanish on and load the translations of the apps the
Shop Floor shows - menus, field labels, statuses - so a worker who picks
Spanish gets it everywhere at once. Odoo's code translations (buttons) come
from files and need nothing; these are the ones kept in the database.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULES = ("base", "web", "mail", "product", "stock", "mrp", "mrp_workorder", "hr",
           "quality", "quality_control", "aa_shop_floor")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            env["res.lang"]._activate_lang("es_419")
            env["ir.module.module"].search(
                [("name", "in", MODULES), ("state", "=", "installed")]
            )._update_translations("es_419")
    except Exception:  # Spanish is a convenience; never fail the update over it
        _logger.exception("aa_shop_floor: could not load Spanish")
