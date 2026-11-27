"""The Springs card was simplified (owner, 2026-11-27): rewrite the stored
card text of every open spring job so it shows the new layout."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    jobs = env["mrp.production"].search([
        ("state", "not in", ("done", "cancel")),
        ("aa_spring_spec_json", "!=", False),
    ])
    jobs._compute_aa_shop_spec()
