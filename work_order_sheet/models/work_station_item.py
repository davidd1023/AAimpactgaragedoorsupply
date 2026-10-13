from odoo import api, fields, models


class WorkStationItem(models.Model):
    """One thing for one bench to make, for one order.

    A SNAPSHOT, NOT A VIEW. The specification is copied onto the row when the
    work is sorted rather than read back from the order every time the kiosk
    loads. Two reasons, and the first is the important one: a description that
    is edited after the work is sorted must not silently change the spring
    somebody is winding. The second is that the bench tablet then loads a
    table and nothing else - no order, no moves, no parsing.
    """

    _name = "work.station.item"
    _description = "Work station item"
    _order = "order_name, station_id, sequence, id"

    station_id = fields.Many2one(
        "work.station", required=True, ondelete="cascade", index=True)
    picking_id = fields.Many2one(
        "stock.picking", required=True, ondelete="cascade", index=True)
    # The order NUMBER, which is what everyone on the floor calls the job.
    order_name = fields.Char(index=True)
    sequence = fields.Integer(default=10)

    product_id = fields.Many2one("product.product", ondelete="restrict")
    # WRITTEN DOWN, not read through product_id. The sheet already decides what
    # a line is called - the thing bought, not the component that moved - and
    # that is what the bench should read.
    name = fields.Char(required=True)
    code = fields.Char(string="Part number")
    quantity = fields.Float(default=1.0)
    uom_name = fields.Char(string="Unit")

    # What to cut, and what it is for. Both are already worked out for the
    # printed sheet; this is the same text.
    length = fields.Char(string="Cut length")
    door = fields.Char(string="Door")
    detail = fields.Text(string="Specification")

    # IDENTITY ACROSS A RE-SORT. Sorting the same transfer twice must not
    # double the queue, and must not lose what a bench has already ticked off,
    # so each row carries the key it was made from and is matched on it.
    line_key = fields.Char(required=True, index=True)

    state = fields.Selection(
        [("todo", "To do"), ("done", "Done")],
        default="todo", required=True, index=True)
    done_at = fields.Datetime(string="Finished", readonly=True)
    company_id = fields.Many2one(
        "res.company", related="picking_id.company_id", store=True, index=True)

    _key_unique = models.Constraint(
        "UNIQUE(picking_id, line_key)",
        "That work is already on a station for this transfer.")

    @api.depends("name", "order_name")
    def _compute_display_name(self):
        for item in self:
            item.display_name = "%s - %s" % (item.order_name or "", item.name)

    def action_done(self):
        self.write({"state": "done", "done_at": fields.Datetime.now()})

        return True

    def action_todo(self):
        """Undo, which a bench tablet needs more than a desk does."""
        self.write({"state": "todo", "done_at": False})

        return True
