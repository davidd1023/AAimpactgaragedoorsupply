"""CUSTOM-LENGTH TRACKS ALREADY ON THE FLOOR GET THEIR TRACK PREP JOB.

Owner, 2026-11-11, on W/O #383 (a 12' x 12' door): the Overview showed no
Track Prep at all, while the order carried a 156" horizontal and a 136"
vertical that Jorge has to cut. A track longer than every prepared one never
had a job - Odoo's route only raises one for the stock lengths - and from this
version confirming an order gives it one.

Orders already confirmed are given theirs here, but only:
  * orders still open (confirmed, not cancelled),
  * whose work has not gone out yet (some transfer still open), and
  * only the TRACK job - `only=("track",)` - so this can never raise a spring,
    kit or cable job somebody chose not to have on an old order.

A line that already has a job is skipped, so running it twice adds nothing.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    custom = env.ref("aa_dealer_orders.product_custom_track", raise_if_not_found=False)
    if not custom:
        return
    lines = env["sale.order.line"].search([
        ("product_id.product_tmpl_id", "=", custom.id),
        ("product_uom_qty", ">", 0),
        ("order_id.state", "=", "sale"),
    ])
    orders = lines.order_id.filtered(
        lambda o: not o.picking_ids or o.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel")))
    if orders:
        orders._aa_create_station_productions(only=("track",))
