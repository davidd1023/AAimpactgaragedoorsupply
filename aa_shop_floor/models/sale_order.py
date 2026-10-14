import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        result = super().action_confirm()
        self._aa_create_spring_productions()
        return result

    def _aa_create_spring_productions(self):
        """One manufacturing order per custom spring line, for the Springs station.

        ONE PER LINE, created here rather than by a Manufacture route, because
        every custom spring is the same product with a different spec: a route
        would merge two orders' springs into one MO and lose a spec. Skips a
        line that already has its MO, so confirming twice makes nothing twice.
        """
        tmpl = self.env.ref("spring_engineering.product_custom_spring", raise_if_not_found=False)
        if not tmpl:
            return
        Production = self.env["mrp.production"].sudo()
        bom = self.env["mrp.bom"].sudo()._aa_custom_spring_bom()
        for order in self:
            lines = order.order_line.filtered(
                lambda l: l.product_id.product_tmpl_id == tmpl
                and l.spring_spec_json
                and l.product_uom_qty > 0
            )
            for line in lines:
                if Production.search_count([("aa_sale_line_id", "=", line.id)]):
                    continue
                values = {
                    "product_id": line.product_id.id,
                    "product_qty": line.product_uom_qty,
                    "bom_id": bom.id,
                    "origin": order.name,
                    "company_id": order.company_id.id,
                    "aa_sale_line_id": line.id,
                    "aa_spring_spec_json": line.spring_spec_json,
                }
                picking_type = order.warehouse_id.manu_type_id
                if picking_type:
                    values["picking_type_id"] = picking_type.id
                try:
                    with self.env.cr.savepoint():
                        production = Production.create(values)
                        production.action_confirm()
                except Exception as error:  # never block the sale over a work order
                    _logger.exception("aa_shop_floor: spring MO for %s failed", order.name)
                    order.message_post(body=_(
                        "The Springs work order for this order could not be created: %s", error))
