"""THE DEALER'S NOTE REACHES THE JOB.

Owner, 2026-10-30: *"when notes are made on the dealer quick order, i cant see
the notes on the manufacturing page for that order, could you fix that."*

It was nowhere downstream. The Quick Order has always stored it into Odoo's
own `sale.order.note`, but `mrp.production` has no note field of its own and
nothing here ever reached back for it.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class OrderNoteOnTheJobCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "A Dealer"})
        self.product = self.env["product.product"].create({
            "name": "A door part", "type": "consu", "is_storable": True})
        self.warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)

    def _order(self, note):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "note": note,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 1})]})

    def _job(self, order, by_line=True):
        """A job raised from a line, or one carrying only a Source Document -
        which is what Odoo's own route leaves."""
        values = {
            "product_id": self.product.id,
            "product_qty": 1.0,
            "picking_type_id": self.warehouse.manu_type_id.id,
            "origin": order.name,
        }

        if by_line:
            values["aa_sale_line_id"] = order.order_line[0].id

        return self.env["mrp.production"].create(values)

    # --- the sentence he wrote ------------------------------------------------

    def test_the_note_is_on_the_job(self):
        """THE ONE THAT SETTLES IT."""
        order = self._order("Cut the tracks two inches short")

        job = self._job(order)

        self.assertIn("Cut the tracks two inches short", job.aa_order_note)

    def test_a_job_with_only_a_source_document_still_finds_it(self):
        """A prepared track job from Odoo's own route carries no sale line."""
        order = self._order("Black track, not white")

        job = self._job(order, by_line=False)

        self.assertFalse(job.aa_sale_line_id)
        self.assertIn("Black track, not white", job.aa_order_note)

    def test_an_order_with_no_note_shows_nothing(self):
        """An empty box is worse than a gap - it reads as something somebody
        forgot to write."""
        job = self._job(self._order(False))

        self.assertFalse(job.aa_order_note)

    def test_an_html_field_that_is_empty_in_html_terms_shows_nothing(self):
        """Odoo leaves `<p><br></p>` behind when somebody clears the editor,
        which is not empty to Python and is empty to a reader."""
        job = self._job(self._order("<p><br></p>"))

        self.assertFalse(job.aa_order_note)

    def test_a_job_with_no_order_at_all_does_not_fall_over(self):
        job = self.env["mrp.production"].create({
            "product_id": self.product.id,
            "product_qty": 1.0,
            "picking_type_id": self.warehouse.manu_type_id.id,
            "origin": "NOT-AN-ORDER"})

        self.assertFalse(job.aa_order_note)

    # --- the line breaks ------------------------------------------------------

    def test_plain_text_keeps_its_line_breaks(self):
        """THE ONE THAT WOULD HAVE GONE WRONG SILENTLY. `sale.order.note` is
        an HTML field, but the Quick Order writes the raw contents of a
        textarea into it. Rendered as HTML, a two-line instruction becomes
        one run-on line - which is how it turns into one wrong one."""
        order = self._order("Cut 2 inches short\nBlack track")

        job = self._job(order)

        # ASSERTED ON THE WRAPPER, because the newline itself survives in
        # the stored value either way - what decides whether a reader sees
        # two lines or one is whether it is rendered with pre-wrap.
        self.assertIn("pre-wrap", job.aa_order_note,
                      "nothing makes the newline a line break, so both "
                      "instructions run together on one line")
        self.assertIn("\n", job.aa_order_note)
        self.assertIn("Cut 2 inches short", job.aa_order_note)
        self.assertIn("Black track", job.aa_order_note)

    def test_sniffing_for_markup_would_not_have_worked(self):
        """Written down because it is the trap: Odoo's Html field has ALREADY
        wrapped a textarea's contents in `<p>...</p>` by the time anything
        reads it, newlines and all. "Does this look like HTML" answers yes
        for both kinds and tells you nothing."""
        order = self._order("one\ntwo")

        self.assertIn("<", order.note, "no tags, so the trap is not real")
        self.assertIn("\n", order.note, "no newline, so the trap is not real")

    def test_a_note_written_in_the_editor_is_left_as_it_is(self):
        """Somebody in the back office uses Odoo's own HTML editor; that
        markup must not be escaped into visible tags."""
        order = self._order("<p>Already <b>formatted</b></p>")

        job = self._job(order)

        self.assertIn("<b>formatted</b>", job.aa_order_note)
        self.assertNotIn("&lt;b&gt;", job.aa_order_note)

    # --- it keeps up -----------------------------------------------------------

    def test_correcting_the_note_shows_on_the_job_at_once(self):
        """Not stored, so an office that corrects a note does not have to
        wait for anything."""
        order = self._order("First thought")
        job = self._job(order)

        order.note = "Second thought"
        job.invalidate_recordset()

        self.assertIn("Second thought", job.aa_order_note)
        self.assertNotIn("First thought", job.aa_order_note)

    # --- where it is -----------------------------------------------------------

    def test_it_is_outside_the_shop_floor_tab(self):
        """That page is hidden unless the job has a shop spec, and a note
        matters on every job there is - a note behind a tab nobody opens is
        the fault this fixes."""
        arch = self.env.ref(
            "aa_shop_floor.mrp_production_form_aa_shop_floor").arch

        before, _sep, after = arch.partition('<xpath expr="//notebook" position="inside">')

        self.assertIn("aa_order_note", before,
                      "the note was put inside the notebook")
