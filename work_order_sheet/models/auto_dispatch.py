import logging

from markupsafe import Markup

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # FINISHED AT THE STATIONS, THEN STRAIGHT TO DISPATCH (owner, 2026-10-19).
    # When the last of an order's manufacturing orders is marked done - from
    # the station or from the Overview - its Work Order is validated on its
    # own, which is what makes the Dispatch appear. Nobody has to remember to
    # press Validate (W/O #203 sat waiting because nobody did).

    def button_mark_done(self):
        result = super().button_mark_done()
        self.filtered(lambda p: p.state == "done")._aa_send_finished_orders_to_dispatch()
        return result

    def _aa_send_finished_orders_to_dispatch(self):
        Sale = self.env["sale.order"].sudo()
        Production = self.env["mrp.production"].sudo()
        for origin in {p.origin for p in self if p.origin}:
            order = Sale.search([("name", "=", origin)], limit=1)
            if not order:
                continue
            productions = Production.search([("origin", "=", origin), ("state", "!=", "cancel")])
            if not productions or any(p.state != "done" for p in productions):
                continue
            for picking in order._aa_work_order_transfers().filtered(
                    lambda p: p.state not in ("done", "cancel")):
                picking._aa_auto_send_to_dispatch()


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _aa_auto_send_to_dispatch(self):
        """Validate this Work Order because every station has finished.

        ONLY WHEN EVERYTHING ON IT IS RESERVED. A line still waiting for stock
        is not guessed at - the Work Order stays where it is and says why, so
        nothing leaves Dispatch short and no stock goes negative.
        Never raises: finishing the job at the station must not fail because
        of the paperwork that follows it.
        """
        self.ensure_one()
        picking = self.sudo()
        try:
            with self.env.cr.savepoint():
                moves = picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel"))
                if any(m.state != "assigned" for m in moves):
                    picking.action_assign()
                if not moves or any(m.state != "assigned" for m in moves):
                    raise UserError(_(
                        "All stations are done, but not everything on this work order "
                        "is in stock yet, so it was not sent to Dispatch. Validate it "
                        "by hand once it is."))
                moves.picked = True
                picking.with_context(
                    skip_backorder=True, picking_ids_not_to_backorder=picking.ids,
                ).button_validate()
                if picking.state != "done":
                    raise UserError(_("Odoo asked a question before validating; validate it by hand."))
        except Exception as error:  # noqa: BLE001 - reported on the record instead
            _logger.info("work_order_sheet: %s not sent to Dispatch: %s", picking.name, error)
            picking.message_post(
                body=Markup("<p>%s</p>") % (error.args[0] if error.args else str(error)),
                subtype_xmlid="mail.mt_note")
            return False
        picking.message_post(
            body=Markup("<p>%s</p>") % _("All stations are done: sent to Dispatch automatically."),
            subtype_xmlid="mail.mt_note")
        return True
