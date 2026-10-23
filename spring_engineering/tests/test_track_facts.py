"""READING A TRACK ON BOTH SIDES OF THE MERGE.

The owner, 2026-10-23: "lets merge the tracks now, they should be separated by
3" and 2", and also track type so horizontal and vertical".

Three pieces of code take a prepared track apart - the dealer Quick Order's
catalogue, the bench card, and the cost refresh - and all three did it with an
anchored regex over the product's NAME. Folding the tracks moves the length
and the finish into variant values and every one of those patterns stops
matching. The bench card is why these tests exist: the length it reads is the
length somebody CUTS TO.

So the facts are read from the name with the chosen values on the end, and
these tests hold that reading still true for the catalogue as it is today -
irregular spacing and all - and for the catalogue as it will be.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TrackFactsCase(TransactionCase):

    def _plain(self, name):
        """A track as the catalogue names it today."""
        return self.env["product.template"].create({
            "name": name, "type": "consu", "is_storable": True,
            "list_price": 100.0, "sale_ok": True}).product_variant_id

    def _folded(self, name, length, colour):
        """A track as it will be: one product, length and colour as values."""
        template = self.env["product.template"].create({
            "name": name, "type": "consu", "is_storable": True,
            "list_price": 100.0, "sale_ok": True})
        for attribute_ref, value in (
            ("spring_engineering.attribute_finish_colour", colour),
            ("spring_engineering.attribute_track_length", length),
        ):
            attribute = self.env.ref(attribute_ref)
            option = self.env["product.attribute.value"].search([
                ("attribute_id", "=", attribute.id), ("name", "=", value)
            ], limit=1) or self.env["product.attribute.value"].create({
                "attribute_id": attribute.id, "name": value})
            self.env["product.template.attribute.line"].create({
                "product_tmpl_id": template.id, "attribute_id": attribute.id,
                "value_ids": [(6, 0, option.ids)]})
        template.invalidate_recordset()

        return template.product_variant_ids[:1]

    # --- the catalogue as it is today -------------------------------------

    def test_todays_names_read_the_same_as_they_always_did(self):
        """Including the irregular spacing: some of his names have two spaces
        after the dash and some have one."""
        for name, want in (
            ('2" Horizontal Track -  120" White',
             {"kind": "horizontal", "size": "2", "length": 120.0,
              "door": None, "colour": "White"}),
            ('3" Horizontal Track - 96" Black',
             {"kind": "horizontal", "size": "3", "length": 96.0,
              "door": None, "colour": "Black"}),
            ("2\" Vertical Track 76\" - 7' Door Height Black",
             {"kind": "vertical", "size": "2", "length": 76.0,
              "door": 7, "colour": "Black"}),
            ("3\" Vertical Track 112\" -  10' Door Height White",
             {"kind": "vertical", "size": "3", "length": 112.0,
              "door": 10, "colour": "White"}),
        ):
            with self.subTest(name=name):
                self.assertEqual(self._plain(name)._aa_track_facts(), want)

    # --- and as it will be ------------------------------------------------

    def test_a_folded_track_reads_the_same_facts(self):
        horizontal = self._folded('2" Horizontal Track', '120"', "White")
        vertical = self._folded(
            '3" Vertical Track', "112\" - 10' Door Height", "Black")

        self.assertEqual(horizontal._aa_track_facts(), {
            "kind": "horizontal", "size": "2", "length": 120.0,
            "door": None, "colour": "White"})
        self.assertEqual(vertical._aa_track_facts(), {
            "kind": "vertical", "size": "3", "length": 112.0,
            "door": 10, "colour": "Black"})

    def test_the_size_is_never_read_as_the_length(self):
        """THE TRAP IN THIS: a track's name opens with 2" or 3", and its
        length is 76" to 132". Reading the first inches figure would cut every
        track to two inches."""
        facts = self._folded('3" Horizontal Track', '96"', "Black")._aa_track_facts()

        self.assertEqual(facts["size"], "3")
        self.assertEqual(facts["length"], 96.0)

    # --- and what must never be read as a prepared track ------------------

    def test_raw_stock_is_refused(self):
        """RAW is the uncut stock a track is cut FROM, and the owner left it
        out of the merge. Reading one as a prepared track would put a 9'6"
        cut on a bench card."""
        raw = self._plain('3" Horizontal Track RAW - 9\'6" Galvanized')

        self.assertIsNone(raw._aa_track_facts())

    def test_a_prepared_cable_is_not_a_track(self):
        """A cable is named for the track it suits - "(8' Door, 3" Track
        (15R))" - and was once printed as a third track for exactly that
        reason."""
        cable = self._plain(
            'Lift Cable 5/32" Pair - Prepared (8\' Door, 3" Track (15R))')

        self.assertIsNone(cable._aa_track_facts())

    def test_something_that_says_too_little_is_refused_not_guessed(self):
        """No finish, no facts. A track whose colour cannot be read gets no
        card rather than a card with the wrong finish on it."""
        bare = self._plain('2" Horizontal Track')

        self.assertIsNone(bare._aa_track_facts())
