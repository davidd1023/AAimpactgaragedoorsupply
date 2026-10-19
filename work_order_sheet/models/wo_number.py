from odoo import api, fields, models

# ONE NUMBER FOR THE WHOLE ORDER (owner, 2026-10-19): "W/O #200". It is given
# when the order is CONFIRMED - paid on the website or sent from the dealer
# Quick Order - and never before, because the sale order's own number (S00035)
# is taken the moment a cart or quotation is opened, so it skips every time a
# cart is abandoned. The floor, the boxes and the dispatch all go by this one;
# the S number stays behind it for invoicing.
#
# NO GAPS: the sequence is no_gap, so a confirmation that fails and rolls back
# gives its number back instead of burning it.
WO_SEQUENCE_CODE = "aa.work.order.number"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    aa_wo_number = fields.Char(
        string="W/O #", copy=False, readonly=True, index=True,
        help="The work order number the shop knows this order by, given when "
             "the order is confirmed.")

    def action_confirm(self):
        # BEFORE super: everything the confirmation makes - the Work Order
        # transfer, the Dispatch, the manufacturing orders - reads it.
        self._aa_assign_wo_number()
        result = super().action_confirm()
        self._aa_name_work_order_transfer()
        return result

    def _aa_assign_wo_number(self):
        sequence = self.env["ir.sequence"].sudo()
        for order in self.sorted("id"):
            if order.aa_wo_number or order.state not in ("draft", "sent"):
                continue
            number = sequence.next_by_code(WO_SEQUENCE_CODE)
            if number:
                order.aa_wo_number = number

    def _aa_work_order_transfers(self):
        """The order's Work Order transfer(s): the warehouse's first step,
        stock to output, which this shop renamed Work Order."""
        self.ensure_one()
        pick_type = self.warehouse_id.pick_type_id
        if not pick_type:
            return self.env["stock.picking"]
        return self.picking_ids.filtered(
            lambda p: p.picking_type_id == pick_type and p.state != "cancel"
        ).sorted("id")

    def _aa_name_work_order_transfer(self):
        """The Work Order transfer is CALLED by the number, so the list under
        Operations > Work Orders reads W/O #200 rather than AAM/WO/00059."""
        for order in self.filtered("aa_wo_number"):
            for index, picking in enumerate(order._aa_work_order_transfers()):
                name = order.aa_wo_number if not index else "%s-%d" % (order.aa_wo_number, index + 1)
                if picking.name != name:
                    picking.name = name


def _order_from_origin(env, origin):
    origin = (origin or "").strip()
    if not origin:
        return env["sale.order"]
    Sale = env["sale.order"].sudo()
    for candidate in (origin, origin.split()[0], origin.split(",")[0]):
        found = Sale.search([("name", "=", candidate.strip())], limit=1)
        if found:
            return found
    return Sale.browse()


class StockPicking(models.Model):
    _inherit = "stock.picking"

    aa_wo_number = fields.Char(
        string="W/O #", compute="_compute_aa_wo_number", store=True, index=True,
        readonly=True)

    @api.depends("origin", "sale_id")
    def _compute_aa_wo_number(self):
        for picking in self:
            order = picking.sale_id or _order_from_origin(picking.env, picking.origin)
            picking.aa_wo_number = order.aa_wo_number or False


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_wo_number = fields.Char(
        string="W/O #", compute="_compute_aa_wo_number", store=True, index=True,
        readonly=True)

    @api.depends("origin")
    def _compute_aa_wo_number(self):
        for production in self:
            order = _order_from_origin(production.env, production.origin)
            production.aa_wo_number = order.aa_wo_number or False
