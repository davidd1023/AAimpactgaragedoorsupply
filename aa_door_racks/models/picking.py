from odoo import _, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super()._action_done()
        out = self.filtered(lambda p: p.picking_type_code == "outgoing" and p.state == "done")
        orders = out.mapped("sale_id")
        if orders:
            doors = self.env["aa.door"].search([
                ("state", "=", "stored"), ("sale_order_id", "in", orders.ids)])
            if doors:
                doors._mark_delivered(_("Left with the dispatch of %s", ", ".join(out.mapped("name"))))
        return res
