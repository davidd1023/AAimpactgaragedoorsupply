import logging

from odoo import _, models

from .mrp_bom import CABLE_OPERATION, HARDWARE_WORKCENTER, KIT_OPERATION

_logger = logging.getLogger(__name__)


# A CUSTOM KIT IS A KIT (owner, 2026-10-20). It is packed at the same bench,
# goes in the same box and gets the same sticker; the only difference is that
# its contents are the order's own lines rather than a phantom BoM. Teaching
# this one sentence about it was cheaper than teaching four modules about a new
# kind of product.
KIT_NAMES = ("hardware kit", "custom kit")


def is_hardware_kit(product):
    name = (product.product_tmpl_id.name or "").lower()

    return any(kit in name for kit in KIT_NAMES)


def is_prepared_cable(product):
    name = (product.product_tmpl_id.name or "").lower()
    return name.startswith("lift cable") and "prepared" in name


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        result = super().action_confirm()
        self._aa_create_station_productions()
        return result

    def _action_cancel(self):
        """Nobody makes anything for an order that has been cancelled.

        THE OTHER HALF OF action_confirm, and it was missing. Confirming an
        order puts a job on the floor for every spring, kit and cable on it;
        cancelling the order left every one of them standing there. Odoo
        cancels the order's TRANSFERS for itself and has never had an opinion
        about manufacturing raised from a sale, so the board kept showing work
        for an order that no longer existed - owner, 2026-10-22: "deleted
        orders still go to shop floor".

        IT IS ALSO THE DELETE CASE. Odoo will not delete a confirmed sale
        order - it has to be cancelled first - so a job that stops on cancel
        is a job that cannot outlive a deletion either.

        THE WIZARD STILL DOES MORE. "Cancel and refund" (aa.order.cancel)
        takes the money back, unwinds done transfers and raises returns. This
        is only the part that cannot be wrong: work nobody has finished, for
        an order nobody is going to pay for.
        """
        result = super()._action_cancel()
        self._aa_cancel_station_productions()

        return result

    def _aa_station_jobs(self):
        """This order's unfinished manufacturing, at any station.

        BY THE SALE LINE AND BY THE ORDER'S NAME. The line is the firm link -
        _aa_create_station_productions writes it - and the name catches the
        jobs Odoo's own routes raise for the same order, which is how the
        cancel-and-refund wizard finds them too.
        """
        Production = self.env["mrp.production"].sudo()
        jobs = Production.browse()

        for order in self:
            jobs |= Production.search([
                ("aa_sale_line_id", "in", order.order_line.ids),
                ("state", "not in", ("done", "cancel")),
            ])

            if order.name:
                jobs |= Production.search([
                    ("origin", "=", order.name),
                    ("state", "not in", ("done", "cancel")),
                ])

        return jobs

    def _aa_cancel_station_productions(self):
        """Stop the jobs, and say so on the order."""
        jobs = self._aa_station_jobs()

        if not jobs:
            return

        stuck = []

        for job in jobs:
            # ONE JOB THAT WILL NOT CANCEL MUST NOT STOP THE CANCEL. A job
            # that has already consumed its components can refuse, and an
            # order held open by a half-made spring is worse than a job
            # somebody has to close by hand - so it is named instead.
            try:
                with self.env.cr.savepoint():
                    job.action_cancel()
            except Exception as error:
                _logger.exception(
                    "aa_shop_floor: cancelling %s with its order failed", job.name)
                stuck.append((job, error))

        for order in self:
            order.message_post(body=_(
                "Shop Floor work stopped with this order: %(names)s.",
                names=", ".join(jobs.mapped("name")),
            ))

        if stuck:
            for order in self:
                order.message_post(body=_(
                    "These would not cancel and need closing by hand:"
                    " %(names)s.",
                    names=", ".join(job.name for job, _error in stuck),
                ))

        jobs._aa_tell_the_shop_floor()

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

    def _aa_cables_by_kit(self, kinds):
        """{kit line: [cable lines]} - the lift cables that go in each kit's box.

        A dealer order lists each door's kit and then that door's extras, so a
        cable belongs to the closest kit line above it (or the first kit when
        it comes before all of them). Cables bought without a kit are not
        boxed and keep a card of their own.
        """
        ordered = sorted(kinds, key=lambda l: (l.sequence, l.id))
        kits = [l for l in ordered if kinds[l] == "kit"]
        result = {}
        if not kits:
            return result
        current = kits[0]
        for line in ordered:
            if kinds[line] == "kit":
                current = line
            elif kinds[line] == "cable":
                result.setdefault(current, []).append(line)
        return result

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
            kinds = {line: self._aa_station_kind(line, spring_tmpl) for line in order.order_line}
            cables_by_kit = self._aa_cables_by_kit(kinds)
            boxed = set().union(*cables_by_kit.values()) if cables_by_kit else set()
            for line in order.order_line:
                kind = kinds[line]
                if not kind or line in boxed \
                        or Production.search_count([("aa_sale_line_id", "=", line.id)]):
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
                    "aa_cable_line_ids": [(6, 0, [c.id for c in cables_by_kit.get(line, [])])],
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
