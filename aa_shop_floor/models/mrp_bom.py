from odoo import api, models

SPRINGS_WORKCENTER = "Springs"
SPRING_OPERATION = "Cut coil, install cones, mark LH/RH"


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    @api.model
    def _aa_custom_spring_bom(self):
        """The BoM that sends a custom spring to the Springs station.

        No components on purpose: spring stock is not consumed through Odoo yet.
        The BoM is only there so the manufacturing order gets one work order at
        the Springs work center. Found by name, created only if missing.
        """
        tmpl = self.env.ref("spring_engineering.product_custom_spring", raise_if_not_found=False)
        if not tmpl:
            return self.browse()
        tmpl = tmpl.sudo()
        Workcenter = self.env["mrp.workcenter"].sudo()
        workcenter = Workcenter.search([("name", "=ilike", SPRINGS_WORKCENTER)], limit=1) \
            or Workcenter.create({"name": SPRINGS_WORKCENTER})

        bom = self.sudo().search([("product_tmpl_id", "=", tmpl.id)], limit=1)
        if not bom:
            bom = self.sudo().create({
                "product_tmpl_id": tmpl.id,
                "product_qty": 1.0,
                "type": "normal",
            })
        if not bom.operation_ids:
            bom.write({"operation_ids": [(0, 0, {
                "name": SPRING_OPERATION,
                "workcenter_id": workcenter.id,
            })]})
        return bom
