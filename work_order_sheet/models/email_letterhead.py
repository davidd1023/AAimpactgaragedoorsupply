"""WHAT EVERY CUSTOMER EMAIL HAS TO CARRY.

The owner, 2026-10-19: the order confirmation, the invoice, "ready for pickup"
and the cancellation should each be in English and carry the AA Impact logo,
the Medley warehouse address, the pickup hours and the W/O number. "These
emails currently use Odoo's generic templates."

SO THE FOUR BODIES ARE OURS, and all four end with one shared block
(work_order_sheet.aa_email_letterhead) rather than four copies of the same
address. Nothing in those bodies is worth hand-editing: the hours are a
setting, the address comes off the warehouse and the logo off the company, so
an update that improves the wording cannot throw away anything the shop typed.

THE W/O NUMBER IS NOT IN THE SAME PLACE TWICE. It lives on the sale order; an
invoice reaches it through the lines it was made from, and a delivery through
the order it belongs to. One small method per model, each tested, rather than
three long expressions buried in XML.
"""

from odoo import api, fields, models

# The owner's own hours, 2026-10-19. A default rather than a constant: the
# field below is his to change when the counter hours change.
DEFAULT_PICKUP_HOURS = "Monday to Friday, 8:00 AM to 4:30 PM"


# The three templates that already existed before this file owned their
# wording. Each was created with noupdate set - Odoo's own two by Odoo, the
# order-ready one by me on the 19th - and a record flagged that way is SKIPPED
# by every later data load, whichever module declares it. That is why the four
# bodies written in customer_emails.xml did nothing at all until this ran: no
# error, no warning, the generic text still going out.
OWNED_TEMPLATES = (
    "sale.mail_template_sale_confirmation",
    "account.email_template_edi_invoice",
    "work_order_sheet.mail_template_order_ready",
)


class IrModelData(models.Model):
    _inherit = "ir.model.data"

    @api.model
    def _aa_own_customer_emails(self):
        """Let customer_emails.xml own the wording of the three it inherited.

        RUN BEFORE THOSE RECORDS, on every update, so the shop's wording is
        re-applied if anything ever puts the generic text back - which an Odoo
        upgrade of `sale` or `account` can do, since clearing this flag also
        lets THEIR data files write again. One `-u work_order_sheet` restores
        it, and this is why that is worth knowing.
        """
        for xmlid in OWNED_TEMPLATES:
            module, _sep, name = xmlid.partition(".")
            row = self.sudo().search(
                [("module", "=", module), ("name", "=", name)], limit=1)

            if row and row.noupdate:
                row.noupdate = False

        return True


class ResCompany(models.Model):
    _inherit = "res.company"

    aa_pickup_hours = fields.Char(
        string="Pickup hours", default=DEFAULT_PICKUP_HOURS,
        help="Printed on every email a customer gets, under the address they "
             "collect from.")


class AaCustomerEmail(models.AbstractModel):
    """Shared by every record that emails a customer.

    ONE SENDING ADDRESS FOR ALL FOUR. The owner set it for the order-ready
    alert on the 19th; a customer who gets four emails from a shop should get
    them from one mailbox, and a reply to any of them should land somewhere
    somebody reads.
    """
    _name = "aa.customer.email"
    _description = "Customer email letterhead"

    def _aa_email_wo_label(self):
        """The W/O number with its label exactly once.

        THE NUMBER CARRIES ITS OWN LABEL. Prod's sequence prints "W/O #202",
        so a template that put "W/O #" in front of it said "W/O #W/O #202" -
        which it did, in the subject line and twice in the body, until a render
        was actually read. Labelled here, once, and only if the number does
        not already say it, so either convention comes out right.
        """
        self.ensure_one()
        number = (self._aa_email_wo_number() or "").strip()

        if not number:
            return ""

        return number if number.upper().startswith("W/O") \
            else "W/O #%s" % number

    def _aa_email_from(self):
        """The address these emails come from, as set in Inventory > Settings."""
        self.ensure_one()
        typed = (self.env["ir.config_parameter"].sudo().get_param(
            "work_order_sheet.ready_email_from") or "").strip()

        return typed or self.company_id.email or ""


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "aa.customer.email"]

    def _aa_email_wo_number(self):
        """The W/O number the shop knows this order by."""
        self.ensure_one()

        return self.aa_wo_number or ""

    def _aa_email_pickup_partner(self):
        """Where the customer collects: the warehouse, or the company."""
        self.ensure_one()

        return (self.warehouse_id.partner_id
                or self.company_id.partner_id)


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "aa.customer.email"]

    def _aa_email_wo_number(self):
        """The W/O number of the order this invoice was made from.

        AN INVOICE CAN COVER MORE THAN ONE ORDER, so the numbers are joined
        rather than guessed between - a customer reading "W/O #200, #201" can
        match both, and one reading only the first would ring up about the
        other.
        """
        self.ensure_one()
        orders = self.invoice_line_ids.sale_line_ids.order_id

        return ", ".join(order.aa_wo_number for order in orders
                         if order.aa_wo_number)

    def _aa_email_pickup_partner(self):
        self.ensure_one()

        return self.company_id.partner_id


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "aa.customer.email"]

    def _aa_email_wo_number(self):
        self.ensure_one()
        order = self.sale_id if "sale_id" in self._fields else False

        return (order.aa_wo_number or "") if order else ""

    def _aa_email_pickup_partner(self):
        self.ensure_one()

        return (self.picking_type_id.warehouse_id.partner_id
                or self.company_id.partner_id)
