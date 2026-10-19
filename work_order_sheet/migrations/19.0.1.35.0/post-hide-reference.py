from odoo import SUPERUSER_ID, api

FLAG = "'aa_hide_reference': True"


def migrate(cr, version):
    """Manufacturing > Work Orders shows W/O # once, not twice (owner,
    2026-10-19). That menu's action was made in the database, not by a
    module, so it is found by what it opens: transfers of the warehouse's
    Work Order type."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    types = env["stock.warehouse"].search([]).pick_type_id
    actions = env["ir.actions.act_window"].search([("res_model", "=", "stock.picking")])
    for action in actions:
        context = (action.context or "").strip()
        if not context.endswith("}") or "aa_hide_reference" in context:
            continue
        if not any("'default_picking_type_id': %d" % t.id in context for t in types):
            continue
        body = context[:-1].rstrip()
        action.context = "%s%s%s}" % (body, ", " if body != "{" else "", FLAG)
