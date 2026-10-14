import logging

from odoo import _, models

from .mrp_bom import CABLE_OPERATION, HARDWARE_WORKCENTER, KIT_OPERATION

_logger = logging.getLogger(__name__)


def is_hardware_kit(product):
    return "hardware kit" in (product.product_tmpl_id.name or "").lower()


def is_prepared_cable(product):
    name = (product.product_tmpl_id.name or "").lower()
    return name.startswith("lift cable") and "prepared" in name


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        result = super().action_confirm()
        self._aa_create_station_productions()
        return result

    def _aa_station_kind(self, line, spring_tmpl):
        """Which Shop Floor station a line goes to, or None."""
        if line.display_type or line.product_uom_qty <= 0 or not line.product_id:
            return None
        if spring_tmpl and line.product_id.product_tmpl_id == spring_tmpl and line.spring_spec_json:
            return "spring"
        if is_hardware_kit(line.product_id):
            return "kit"
        if is_prepared_cable(line.product_id):
            return "cable"
        return None

    def _aa_create_station_productions(self):
        """One manufacturing order per line that a station has to prepare.

        Springs: custom springs from Spring Engineering.
        Hardware: hardware kits (pack the box) and prepared lift cable pairs (cut).

        ONE PER LINE, created here rather than by a Manufacture route, because
        every custom spring is the same product with a different spec: a route
        would merge two orders' springs into one MO and lose a spec. Skips a
        line that already has its MO, so confirming twice makes nothing twice.
        """
        spring_tmpl = self.env.ref("spring_engineering.product_custom_spring", raise_if_not_found=False)
        Production = self.env["mrp.production"].sudo()
        Bom = self.env["mrp.bom"].sudo()
        for order in self:
            for line in order.order_line:
                kind = self._aa_station_kind(line, spring_tmpl)
                if not kind or Production.search_count([("aa_sale_line_id", "=", line.id)]):
                    continue
                if kind == "spring":
                    bom = Bom._aa_custom_spring_bom()
                elif kind == "kit":
                    bom = Bom._aa_station_bom(line.product_id.product_tmpl_id, HARDWARE_WORKCENTER, KIT_OPERATION)
                else:
                    bom = Bom._aa_station_bom(line.product_id.product_tmpl_id, HARDWARE_WORKCENTER, CABLE_OPERATION)
                values = {
                    "product_id": line.product_id.id,
                    "product_qty": line.product_uom_qty,
                    "bom_id": bom.id,
                    "origin": order.name,
                    "company_id": order.company_id.id,
                    "aa_sale_line_id": line.id,
                    "aa_station_kind": kind,
                    "aa_spring_spec_json": line.spring_spec_json if kind == "spring" else False,
                }
                picking_type = order.warehouse_id.manu_type_id
                if picking_type:
                    values["picking_type_id"] = picking_type.id
                try:
                    with self.env.cr.savepoint():
                        production = Production.create(values)
                        production.action_confirm()
                except Exception as error:  # never block the sale over a work order
                    _logger.exception("aa_shop_floor: %s MO for %s failed", kind, order.name)
                    order.message_post(body=_(
                        "The Shop Floor work order for %(line)s could not be created: %(error)s",
                        line=line.product_id.display_name, error=error))
