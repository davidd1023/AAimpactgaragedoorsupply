"""THE DEALER'S OWN NOTE, ON THE JOB THAT HAS TO READ IT.

Owner, 2026-10-30: *"when notes are made on the dealer quick order, i cant see
the notes on the manufacturing page for that order, could you fix that."*

**IT WAS NOWHERE DOWNSTREAM.** The Quick Order has always stored it - into
Odoo's own `sale.order.note` (`aa_dealer_orders/controllers.py`, trimmed to
2000 characters) - but `mrp.production` has NO note field of its own, and
nothing here ever reached back for it. The note sat on the order, where only
the office ever looks.

**THE JOB FINDS ITS ORDER TWO WAYS**, the same as everything else that has to:
`aa_sale_line_id` when the job was raised from a line, and the Source Document
by name when it was not - a prepared track job from Odoo's own route carries
nothing else.

**NOT STORED.** It is read when somebody opens the job, so an office that
corrects the note sees the correction on the bench's screen immediately
rather than at the next recompute. There is nothing to search or sort on
here; it is a paragraph a man reads before he builds.

**ITS LINE BREAKS WOULD HAVE BEEN LOST, SILENTLY.** `sale.order.note` is an
HTML field - Odoo calls it "Terms and conditions" - but what the Quick Order
writes into it is the raw contents of a textarea. In HTML a newline is
whitespace, so "cut 2 inches short\nblack track" renders as ONE RUN-ON LINE,
which is how a two-line instruction becomes one wrong one.

**AND SNIFFING FOR MARKUP DOES NOT WORK**, which a test found rather than
reasoning: Odoo's Html field has ALREADY wrapped the textarea's contents in
`<p>...</p>` by the time anything reads it, newlines and all. So "does this
look like HTML" answers yes for both cases and tells you nothing.

So nothing is sniffed and nothing is converted. The note is wrapped in
`white-space: pre-wrap`, under which a literal newline becomes a line break
and real markup still renders as markup. Both kinds come out right, and
neither is rewritten.
"""

from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools.mail import is_html_empty


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_order_note = fields.Html(
        string="Note From The Order", compute="_compute_aa_order_note",
        sanitize=False, readonly=True,
        help="What the dealer typed in the Notes box of the Quick Order, or "
             "whatever is on the sale order's note.")

    @api.depends("aa_sale_line_id", "origin")
    def _compute_aa_order_note(self):
        for production in self:
            order = production._aa_note_order()
            note = order.note if order else False

            if not note or is_html_empty(note):
                production.aa_order_note = False
                continue

            # PRE-WRAP, so a textarea's newlines are line breaks and the
            # editor's markup is still markup. Nothing is rewritten.
            production.aa_order_note = Markup(
                '<div style="white-space: pre-wrap;">%s</div>') % Markup(note)

    def _aa_note_order(self):
        """The order behind this job, by line or by Source Document."""
        self.ensure_one()

        if self.aa_sale_line_id:
            return self.aa_sale_line_id.order_id

        origin = (self.origin or "").strip()

        if not origin:
            return self.env["sale.order"].browse()

        return self.env["sale.order"].search(
            [("name", "=", origin)], limit=1)
