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


@tagged("post_install", "-at_install")
class TrackFamiliesCase(TransactionCase):
    """The four track families, assembled from the catalogue rather than
    listed - because his track names are too irregular to transcribe and he
    keeps adding lengths."""

    def _track(self, name, code=None, stock=0.0):
        template = self.env["product.template"].create({
            "name": name, "default_code": code, "type": "consu",
            "is_storable": True, "list_price": 122.75, "sale_ok": True,
            "is_published": True})
        if stock:
            quant = self.env["stock.quant"].with_context(
                inventory_mode=True).create({
                    "product_id": template.product_variant_id.id,
                    "location_id": self.env.ref("stock.stock_location_stock").id,
                    "inventory_quantity": stock})
            quant.action_apply_inventory()

        return template

    def _catalogue(self):
        """His tracks as the catalogue spells them - including the two
        spaces after the dash that some rows have and some do not."""
        for size in ("2", "3"):
            for length, colour, gap in (
                (96, "Black", " "), (96, "White", "  "),
                (108, "Black", " "), (108, "White", " "),
                (120, "Black", " "), (120, "White", "  "),
                (132, "Black", " "), (132, "White", " "),
            ):
                self._track('%s" Horizontal Track -%s%d" %s'
                            % (size, gap, length, colour),
                            code='CH-HT-%s"' % size,
                            stock=40 if colour == "Black" else 10)
            for length, door, colour in (
                (76, 7, "Black"), (76, 7, "White"),
                (88, 8, "Black"), (88, 8, "White"),
                (100, 9, "Black"), (100, 9, "White"),
                (112, 10, "Black"), (112, 10, "White"),
            ):
                self._track("%s\" Vertical Track %d\" - %d' Door Height %s"
                            % (size, length, door, colour),
                            code='CH-VT-%s"' % size,
                            stock=40 if colour == "Black" else 10)
        self._track('3" Horizontal Track RAW - 9\'6" Galvanized', stock=60)

    def _family(self, survivor):
        return next(
            (spec for spec in self.env["product.template"]._aa_track_families()
             if spec["survivor"] == survivor), None)

    def test_four_families_come_out_of_the_catalogue(self):
        """2" and 3", horizontal and vertical - which is what he asked for."""
        self._catalogue()

        names = [spec["survivor"]
                 for spec in self.env["product.template"]._aa_track_families()]

        self.assertEqual(sorted(names), [
            '2" Horizontal Track', '2" Vertical Track',
            '3" Horizontal Track', '3" Vertical Track'])

    def test_raw_stock_is_not_swept_in(self):
        """It is what a track is cut from, and he kept it out."""
        self._catalogue()

        for spec in self.env["product.template"]._aa_track_families():
            for name in spec["products"]:
                self.assertNotIn("RAW", name, spec["survivor"])

    def test_the_lengths_read_in_the_order_a_person_reads_them(self):
        """96 before 108, which sorting the text the other way round does
        not give you."""
        self._catalogue()

        self.assertEqual(
            self._family('2" Horizontal Track')["value_order"][
                "attribute_track_length"],
            ['96"', '108"', '120"', '132"'])

    def test_a_vertical_track_keeps_the_door_it_is_for(self):
        """The catalogue has always said "76" - 7' Door Height", the floor
        reads the height back out of it, and a customer picks a track by the
        door rather than by inches."""
        self._catalogue()

        self.assertEqual(
            self._family('3" Vertical Track')["value_order"][
                "attribute_track_length"][0],
            "76\" - 7' Door Height")

    # --- and the merge itself ---------------------------------------------

    def _merge(self, survivor):
        reports = self.env["product.template"]._aa_merge_variant_families(
            dry_run=False, only=[survivor])
        self.assertEqual(len(reports), 1, reports)

        return reports[0]

    def test_a_track_family_merges_into_one_product(self):
        self._catalogue()

        report = self._merge('2" Horizontal Track')

        self.assertEqual(report["state"], "merged", report)
        merged = self.env["product.template"].search(
            [("name", "=", '2" Horizontal Track')], limit=1)
        self.assertEqual(len(merged.product_variant_ids), 8)
        self.assertEqual(
            sorted(merged.attribute_line_ids.attribute_id.mapped("name")),
            ["Colour", "Length"])

    def test_the_floor_can_still_read_a_merged_track(self):
        """THE ONE THAT MATTERS. The length on a bench card is the length
        somebody cuts to, and after the merge it lives in a variant value
        rather than in the name."""
        self._catalogue()
        self._merge('3" Vertical Track')

        merged = self.env["product.template"].search(
            [("name", "=", '3" Vertical Track')], limit=1)

        read = [variant._aa_track_facts()
                for variant in merged.product_variant_ids]
        self.assertTrue(all(read), "a merged track could not be read")
        self.assertEqual({facts["size"] for facts in read}, {"3"})
        self.assertEqual({facts["kind"] for facts in read}, {"vertical"})
        self.assertEqual({facts["length"] for facts in read},
                         {76.0, 88.0, 100.0, 112.0})
        self.assertEqual({facts["door"] for facts in read}, {7, 8, 9, 10})
        self.assertEqual({facts["colour"] for facts in read},
                         {"Black", "White"})

    def test_the_stock_lands_on_the_right_length_and_colour(self):
        self._catalogue()
        self._merge('2" Vertical Track')

        merged = self.env["product.template"].search(
            [("name", "=", '2" Vertical Track')], limit=1)

        for variant in merged.product_variant_ids:
            facts = variant._aa_track_facts()
            want = 40.0 if facts["colour"] == "Black" else 10.0
            self.assertEqual(
                variant.qty_available, want,
                "%s %s" % (facts["length"], facts["colour"]))

    def test_a_merged_family_says_so_next_time(self):
        """It is read off the catalogue, so the archived originals are what
        it finds - and the merged product is what tells it the work is done."""
        self._catalogue()
        self._merge('2" Horizontal Track')

        again = self._merge('2" Horizontal Track')

        self.assertEqual(again["state"], "already merged", again)
        self.assertEqual(again["variants"], 8, again)
