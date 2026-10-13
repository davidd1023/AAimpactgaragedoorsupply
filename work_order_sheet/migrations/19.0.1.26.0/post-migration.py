from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Leave the work that is already on the benches where it is.

    Showing an order on a station is now something the office does on purpose,
    and every existing order would otherwise answer "no" to a question nobody
    had asked them - the floor would come in to find today's queues empty.

    So every open transfer that already carries station work is treated as
    sent, which is what the benches could see the day before. The new rule
    applies from here on, to orders confirmed after it.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    live = env["stock.picking"].search([
        ("state", "not in", ("done", "cancel")),
        ("work_station_item_ids", "!=", False),
        ("work_station_released", "=", False),
    ])

    if live:
        live.write({"work_station_released": True})
