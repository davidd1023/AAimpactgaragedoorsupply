from odoo import SUPERUSER_ID, api

# What the benches put on the screen. The rows they produced are left where
# they are - they are a record of work that was done - but nothing points at
# them any more.
HIDE = (
    "work_order_sheet.menu_work_station_item",
    "work_order_sheet.menu_work_station",
    "work_order_sheet.view_picking_form_work_stations_parts",
    "work_order_sheet.vpicktree_work_stations_parts",
    "work_order_sheet.view_picking_internal_search_work_stations_parts",
)
DROP = (
    "work_order_sheet.action_picking_station_sync",
    "work_order_sheet.action_picking_station_withdraw",
)


def migrate(cr, version):
    """Take the work stations off the screen, keeping everything they made.

    The owner put the benches away in favour of the shop floor module. The
    files that create these records no longer load, which is enough for a
    database installed from here on and nothing at all for one that already
    has them: a menu stays in the menu, a view inherit keeps applying, an
    action keeps appearing under Actions.

    ARCHIVED, NOT DELETED, wherever a record can be - unarchiving is how the
    benches come back, and it keeps the ids the data files would reuse. The
    two server actions have no archive flag, so those are removed; the data
    file recreates them.

    The work.station records themselves are archived last, which also takes
    their kiosk links out of use - though the routes are already gone.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    for xmlid in HIDE:
        record = env.ref(xmlid, raise_if_not_found=False)

        if record and "active" in record._fields and record.active:
            record.active = False

    for xmlid in DROP:
        record = env.ref(xmlid, raise_if_not_found=False)

        if record:
            record.unlink()

    stations = env["work.station"].search([])

    if stations:
        stations.active = False
