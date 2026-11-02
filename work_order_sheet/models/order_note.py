"""THE DEALER'S NOTE, ON THE TRANSFER THE SHOP ACTUALLY OPENS.

Owner, 2026-10-30: *"i dont see the note, could you put it on this tab and on
the work order sheet as well"* - with a screenshot of **W/O #299**.

**I PUT IT ON THE WRONG MODEL.** He had asked for "the manufacturing page for
that order", and the first build answered that with `mrp.production`. The
screenshot settles it: Check Availability, Validate, Return, a Source and a
Destination Location, a PO Number, Source Document S00141 - that is a
**`stock.picking`**, shown under Manufacturing > Work Orders. The note was on
a record he never opens.

The same mistake as the sticker's host: a screen was described and I decided
which model it was instead of looking. **The picture settles what the words
cannot.**

**IT IS READ-ONLY, BESIDE ODOO'S OWN NOTE, NOT WRITTEN INTO IT.** Copying the
order's note into `stock.picking.note` would have put it on exactly the tab
he pointed at - and then there would be TWO of them: a copy going stale the
moment the office corrects the order, and no way to tell whose words were
whose once somebody typed their own remark underneath. The transfer's own
note stays the shop's to write in; the dealer's is shown above it and comes
straight off the order every time it is read.
"""

from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools.mail import is_html_empty


def readable_note(note):
    """An order note as something a person can read, or False.

    **ITS LINE BREAKS WOULD BE LOST, SILENTLY.** `sale.order.note` is an HTML
    field, but what the dealer Quick Order writes into it is the raw contents
    of a textarea, and in HTML a newline is whitespace: "cut 2 inches
    short\\nblack track" renders as ONE RUN-ON LINE, which is how a two-line
    instruction becomes one wrong one.

    **AND SNIFFING FOR MARKUP DOES NOT WORK** - a test found that rather than
    reasoning. Odoo's Html field has ALREADY wrapped the textarea's contents
    in `<p>...</p>` by the time anything reads it, newlines and all, so "does
    this look like HTML" answers yes for both kinds and tells you nothing.

    So nothing is sniffed and nothing is rewritten: `white-space: pre-wrap`
    makes a literal newline a line break and leaves real markup as markup.

    Lives HERE because `aa_shop_floor` depends on this module and shows the
    same note on the manufacturing order; one copy, so the two cannot drift.
    """
    if not note or is_html_empty(note):
        return False

    return Markup('<div style="white-space: pre-wrap;">%s</div>') % Markup(note)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    aa_order_note = fields.Html(
        string="Note From The Order", compute="_compute_aa_order_note",
        sanitize=False, readonly=True,
        help="What the dealer typed in the Notes box of the Quick Order. It "
             "comes off the sale order, so correcting it there corrects it "
             "here.")

    @api.depends("sale_id.note", "origin")
    def _compute_aa_order_note(self):
        for picking in self:
            order = picking._work_order_sale_order()
            picking.aa_order_note = readable_note(order.note if order else False)
