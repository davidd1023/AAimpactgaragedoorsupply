from odoo import api, models

SPRINGS_WORKCENTER = "Springs"
HARDWARE_WORKCENTER = "Hardware"
SPRING_OPERATION = "Cut coil, install cones, mark LH/RH"
KIT_OPERATION = "Pack hardware kit"
CABLE_OPERATION = "Cut lift cables, sleeve, thimble, stop"


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    @api.model
    def _aa_station_bom(self, tmpl, workcenter_name, operation_name):
        """A NORMAL BoM with no components and one operation at a work center.

        Only there so a manufacturing order lands on that Shop Floor station.
        No components on purpose: stock is consumed by the delivery (kits and
        prepared cables explode their own KIT BoMs there), not by this order.
        Kit (phantom) BoMs are never touched - the delivery only looks at those.
        Found by its operation's work center, created only if missing.
        """
        tmpl = tmpl.sudo()
        Workcenter = self.env["mrp.workcenter"].sudo()
        workcenter = Workcenter.search([("name", "=ilike", workcenter_name)], limit=1) \
            or Workcenter.create({"name": workcenter_name})

        boms = self.sudo().search([
            ("product_tmpl_id", "=", tmpl.id),
            ("product_id", "=", False),
            ("type", "=", "normal"),
        ])
        bom = boms.filtered(lambda b: workcenter in b.operation_ids.workcenter_id)[:1] \
            or boms.filtered(lambda b: not b.operation_ids and not b.bom_line_ids)[:1]
        if not bom:
            bom = self.sudo().create({
                "product_tmpl_id": tmpl.id,
                "product_qty": 1.0,
                "type": "normal",
            })
        if not bom.operation_ids:
            bom.write({"operation_ids": [(0, 0, {
                "name": operation_name,
                "workcenter_id": workcenter.id,
            })]})
        return bom

    @api.model
    def _aa_custom_spring_bom(self):
        """The BoM that sends a custom spring to the Springs station."""
        tmpl = self.env.ref("spring_engineering.product_custom_spring", raise_if_not_found=False)
        if not tmpl:
            return self.browse()
        return self._aa_station_bom(tmpl, SPRINGS_WORKCENTER, SPRING_OPERATION)
