"""FOLDING COLOURS, SIZES AND HANDS INTO ONE PRODUCT, WITHOUT LOSING ANYTHING.

The merge in models/product_variant_merge.py rewrites the catalogue: it turns
81 products into 15 and moves stock, part numbers, costs, prices, kit BoM
lines, reordering rules, draft paperwork and a setting onto new variants. The
risk is not that it fails loudly - it is that it half-works and nobody sees:
a count landing on the wrong colour, or a kit quietly picking the left-hand
bracket because something matched by position.

So these tests are about what must SURVIVE the merge, product by product, and
about the merge refusing a family it cannot do properly.

The families here are the owner's own, with his part numbers, but the prices
are made up: his real ones were already checked to be additive (colour never
moves a price, size always does) and the test needs to prove the arithmetic
both ways, which means it needs a family that does not add up too.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVariantMerge(TransactionCase):

    def setUp(self):
        super().setUp()
        self.stock = self.env.ref("stock.stock_location_stock")
        self.other = self.env["stock.location"].create({
            "name": "Rack B", "usage": "internal",
            "location_id": self.stock.id,
        })

    # --- the fixture ----------------------------------------------------

    def _product(self, name, code=None, price=1.0, cost=0.5, stock=0.0,
                 location=None):
        tmpl = self.env["product.template"].create({
            "name": name,
            "default_code": code,
            "type": "consu",
            "is_storable": True,
            "list_price": price,
            "standard_price": cost,
            "sale_ok": True,
            "is_published": True,
        })
        if stock:
            self._put(tmpl.product_variant_id, stock, location or self.stock)
        return tmpl

    def _put(self, variant, quantity, location):
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": variant.id,
            "location_id": location.id,
            "inventory_quantity": quantity,
        })
        quant.action_apply_inventory()

    def _on_hand(self, variant, location=None):
        domain = [("product_id", "=", variant.id)]
        if location:
            domain.append(("location_id", "=", location.id))
        else:
            domain.append(("location_id.usage", "in", ("internal", "transit")))
        return sum(self.env["stock.quant"].search(domain).mapped("quantity"))

    def _anchor_brackets(self):
        """The owner's own example: one bracket, two hands, two colours."""
        made = {}
        for hand in ("LH", "RH"):
            for colour, qty in (("Black", 200.0), ("White", 90.0)):
                name = "Spring Anchor Bracket %s %s" % (hand, colour)
                made[name] = self._product(
                    name, code="CH1119D", price=6.91, cost=3.10,
                    stock=qty + (1.0 if hand == "RH" else 0.0),
                )
        return made

    def _jamb_brackets(self):
        """Four sizes, two colours, and a price that climbs with the size."""
        made = {}
        for size, price in (("10", 1.20), ("12", 1.36), ("14", 1.61), ("16", 1.91)):
            for colour, qty in (("Black", 800.0), ("White", 330.0)):
                name = "Jamb Bracket # %s %s" % (size, colour)
                made[name] = self._product(
                    name, code="CH1108", price=price, cost=price / 2,
                    stock=qty + float(size),
                )
        return made

    def _hinges(self):
        """Seven sizes, three colours, and a part number per SIZE."""
        made = {}
        for n in range(1, 8):
            for colour in ("Black", "White", "Galvanized"):
                name = "Hinge # %d %s" % (n, colour)
                made[name] = self._product(
                    name, code="CH1411-%d" % n, price=2.4 + n * 0.1,
                    cost=1.0 + n * 0.05, stock=100.0 + n,
                )
        return made

    def _merge(self, survivor, dry_run=False):
        reports = self.env["product.template"]._aa_merge_variant_families(
            dry_run=dry_run, only=[survivor]
        )
        self.assertEqual(len(reports), 1, reports)
        return reports[0]

    def _survivor(self, name):
        return self.env["product.template"].with_context(
            active_test=False, lang="en_US"
        ).search([("name", "=", name)])

    def _live_variants(self, survivor):
        """The variants on the shop page: the archived original that stays
        behind to hold its history is not one of them."""
        return self._survivor(survivor).with_context(
            active_test=True).product_variant_ids

    def _variant(self, survivor, **combo):
        """The variant of the merged product with these choices, by NAME."""
        for variant in self._live_variants(survivor):
            got = {
                ptav.attribute_id.name: ptav.name
                for ptav in variant.product_template_attribute_value_ids
            }
            if got == combo:
                return variant
        return self.env["product.product"]

    # --- what the owner asked for ---------------------------------------

    def test_one_bracket_with_a_hand_and_a_colour_to_choose(self):
        """"there will only be one spring anchor bracket rh but with two color
        choices" - and, since 2026-10-21, the hand is a choice on it too."""
        self._anchor_brackets()

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "merged", report)
        survivor = self._survivor("Spring Anchor Bracket")
        self.assertTrue(survivor.active)
        self.assertEqual(len(self._live_variants("Spring Anchor Bracket")), 4)
        # The base's own original variant stays, archived, because a done
        # stock move still points at it.
        self.assertEqual(
            len(survivor.with_context(active_test=False).product_variant_ids), 5)
        self.assertEqual(
            sorted(survivor.attribute_line_ids.attribute_id.mapped("name")),
            ["Colour", "Hand"],
        )
        # The four old products are gone from the shop, not deleted.
        olds = self.env["product.template"].with_context(active_test=False).search(
            [("name", "=like", "Spring Anchor Bracket %")]
        )
        self.assertEqual(len(olds), 3, olds.mapped("name"))
        self.assertFalse(any(olds.mapped("active")))
        self.assertFalse(any(olds.mapped("is_published")))
        self.assertTrue(survivor.is_published)

    def test_the_stock_lands_on_the_right_colour_and_the_right_hand(self):
        """THE TEST THIS WHOLE THING EXISTS FOR. A count on the wrong hand is
        invisible on screen and wrong in the rack."""
        self._anchor_brackets()

        self._merge("Spring Anchor Bracket")

        self.assertEqual(self._on_hand(self._variant(
            "Spring Anchor Bracket", Hand="RH", Colour="Black")), 201.0)
        self.assertEqual(self._on_hand(self._variant(
            "Spring Anchor Bracket", Hand="RH", Colour="White")), 91.0)
        self.assertEqual(self._on_hand(self._variant(
            "Spring Anchor Bracket", Hand="LH", Colour="Black")), 200.0)
        self.assertEqual(self._on_hand(self._variant(
            "Spring Anchor Bracket", Hand="LH", Colour="White")), 90.0)

    def test_stock_keeps_the_location_it_was_in(self):
        """Stock is moved per location, not totalled and dumped in one."""
        made = self._anchor_brackets()
        white = made["Spring Anchor Bracket LH White"].product_variant_id
        self._put(white, 7.0, self.other)

        self._merge("Spring Anchor Bracket")

        variant = self._variant("Spring Anchor Bracket", Hand="LH", Colour="White")
        self.assertEqual(self._on_hand(variant, self.stock), 90.0)
        self.assertEqual(self._on_hand(variant, self.other), 7.0)

    def test_nothing_is_counted_twice(self):
        """The old product must be left at nothing: stock on both records for
        even a moment is stock on the books twice."""
        made = self._anchor_brackets()
        old = made["Spring Anchor Bracket RH Black"].product_variant_id

        self._merge("Spring Anchor Bracket")

        self.assertEqual(self._on_hand(old), 0.0)

    def test_each_variant_keeps_its_own_part_number_and_cost(self):
        """Hinges have a part number PER SIZE - CH1411-1 to CH1411-7 - so the
        number cannot live on the product; it lives on each variant."""
        self._hinges()

        self._merge("Hinge")

        for n in range(1, 8):
            for colour in ("Black", "White", "Galvanized"):
                variant = self._variant("Hinge", **{
                    "Hinge Size": "#%d" % n, "Colour": colour})
                self.assertTrue(variant, "no variant for #%d %s" % (n, colour))
                self.assertEqual(variant.default_code, "CH1411-%d" % n)
                self.assertAlmostEqual(variant.standard_price, 1.0 + n * 0.05, 2)
                self.assertEqual(self._on_hand(variant), 100.0 + n)

    def test_every_variant_costs_what_its_old_product_cost(self):
        """Size moves the price, colour does not - and the page has to charge
        exactly what the four old products charged."""
        self._jamb_brackets()

        self._merge("Jamb Bracket")

        for size, price in (("#10", 1.20), ("#12", 1.36), ("#14", 1.61), ("#16", 1.91)):
            for colour in ("Black", "White"):
                variant = self._variant("Jamb Bracket", **{
                    "Bracket Size": size, "Colour": colour})
                self.assertAlmostEqual(
                    variant.lst_price, price, 2,
                    "%s %s should still be %s" % (size, colour, price))

    def test_the_sizes_are_offered_in_the_order_a_person_reads_them(self):
        """#10 before #16, which is not what sorting gives you."""
        self._jamb_brackets()

        self._merge("Jamb Bracket")

        line = self._survivor("Jamb Bracket").attribute_line_ids.filtered(
            lambda l: l.attribute_id.name == "Bracket Size")
        self.assertEqual(
            line.product_template_value_ids.sorted(
                lambda v: v.product_attribute_value_id.sequence).mapped("name"),
            ["#10", "#12", "#14", "#16"],
        )

    # --- what must not get lost ------------------------------------------

    def test_a_kit_bom_line_follows_the_exact_part_it_pointed_at(self):
        """A KIT MUST NOT CHANGE HANDS. The BoM line said RH Black; after the
        merge it has to say the RH Black VARIANT, not whichever came first."""
        made = self._anchor_brackets()
        kit = self._product("Test Hardware Kit", code="HK-TEST", price=100.0)
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": kit.id,
            "type": "normal",
            "bom_line_ids": [(0, 0, {
                "product_id": made["Spring Anchor Bracket RH Black"].product_variant_id.id,
                "product_qty": 2.0,
            })],
        })

        self._merge("Spring Anchor Bracket")

        want = self._variant("Spring Anchor Bracket", Hand="RH", Colour="Black")
        self.assertEqual(bom.bom_line_ids.product_id, want)
        self.assertEqual(
            bom.bom_line_ids.product_id.product_template_attribute_value_ids
            .filtered(lambda p: p.attribute_id.name == "Hand").name,
            "RH",
            "the kit changed hands in the merge",
        )

    def test_a_reordering_rule_follows_its_product(self):
        made = self._anchor_brackets()
        variant = made["Spring Anchor Bracket LH White"].product_variant_id
        rule = self.env["stock.warehouse.orderpoint"].create({
            "product_id": variant.id,
            "location_id": self.stock.id,
            "product_min_qty": 10.0,
            "product_max_qty": 50.0,
        })

        self._merge("Spring Anchor Bracket")

        self.assertEqual(
            rule.product_id,
            self._variant("Spring Anchor Bracket", Hand="LH", Colour="White"),
        )

    def test_a_draft_quotation_follows_but_a_confirmed_one_does_not(self):
        """An open quote should sell the product that now has the stock. A
        confirmed order is a record of what was sold and stays as it is."""
        made = self._anchor_brackets()
        variant = made["Spring Anchor Bracket RH White"].product_variant_id
        partner = self.env["res.partner"].create({"name": "Merge Test Customer"})
        draft = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [(0, 0, {"product_id": variant.id, "product_uom_qty": 1})],
        })
        done = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [(0, 0, {"product_id": variant.id, "product_uom_qty": 1})],
        })
        done.action_confirm()
        # The delivery it booked would stop the family, and rightly so - this
        # test is about the order line, so take the picking out of the way.
        done.picking_ids.action_cancel()

        self._merge("Spring Anchor Bracket")

        want = self._variant("Spring Anchor Bracket", Hand="RH", Colour="White")
        self.assertEqual(draft.order_line.product_id, want)
        self.assertEqual(done.order_line.product_id, variant)

    def test_the_flag_angle_setting_follows_its_product(self):
        """The prepared-track flag angle is stored in a setting as a product
        id. Archive the product it names and prepared tracks lose their flag
        angle with nothing failing."""
        made = {}
        for size in ('5.9"', '6-3/8"'):
            for colour in ("Black", "White"):
                name = "Flag Angle %s %s" % (size, colour)
                made[name] = self._product(
                    name, price=9.1 if size == '5.9"' else 9.22, stock=50.0)
        named = made['Flag Angle 5.9" White'].product_variant_id
        self.env["ir.config_parameter"].sudo().set_param(
            "spring_engineering.track_prep_flag_product_id", str(named.id))

        self._merge("Flag Angle")

        want = self._variant("Flag Angle", **{
            "Flag Angle Size": '5.9"', "Colour": "White"})
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(
                "spring_engineering.track_prep_flag_product_id"),
            str(want.id),
        )

    # --- refusing to do it badly -----------------------------------------

    def test_a_family_that_cannot_be_priced_by_attribute_is_left_alone(self):
        """If a white bracket ever costs more than a black one, the price
        cannot be expressed as "product plus choices". Say so; change nothing.
        """
        made = self._anchor_brackets()
        made["Spring Anchor Bracket LH White"].list_price = 8.50

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "skipped", report)
        self.assertTrue(
            any("cannot be priced" in p for p in report["problems"]), report)
        for tmpl in made.values():
            self.assertTrue(tmpl.active, "%s was touched anyway" % tmpl.name)
            self.assertFalse(tmpl.attribute_line_ids)

    def test_an_open_delivery_stops_the_family(self):
        """We are about to move this stock to another product. A picking that
        has not gone out has a claim on it."""
        made = self._anchor_brackets()
        variant = made["Spring Anchor Bracket RH Black"].product_variant_id
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.env.ref("stock.picking_type_out").id,
            "location_id": self.stock.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "move_ids": [(0, 0, {
                "product_id": variant.id,
                "product_uom_qty": 5.0,
                "location_id": self.stock.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            })],
        })
        picking.action_confirm()

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "skipped", report)
        self.assertTrue(
            any("still open" in p for p in report["problems"]), report)
        self.assertEqual(self._on_hand(variant), 201.0, "stock was moved anyway")

    def test_a_product_missing_from_the_catalogue_stops_the_family(self):
        """Half a family is worse than none: the store would offer variants
        with nobody's stock on them."""
        made = self._anchor_brackets()
        made["Spring Anchor Bracket LH Black"].name = "Anchor Bracket, old"

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "skipped", report)
        self.assertTrue(
            any("not in the catalogue" in p for p in report["problems"]), report)

    def test_a_colour_added_after_the_table_was_written_is_reported(self):
        """A sibling nobody mapped would be orphaned by the merge. It is left
        alone and said out loud."""
        self._hinges()
        self._product("Hinge # 8 Brown", code="CH1411-8", price=3.5)

        report = self._merge("Hinge")

        self.assertEqual(report["state"], "merged", report)
        self.assertTrue(
            any("Hinge # 8 Brown" in n for n in report["notes"]), report)
        self.assertTrue(
            self._survivor("Hinge # 8 Brown").active,
            "the stray was swept up instead of being left alone")

    # --- the rehearsal ----------------------------------------------------

    def test_the_rehearsal_reports_without_changing_anything(self):
        """The dry run performs the merge and rolls it back, so what it
        reports is what happened rather than what somebody expected."""
        made = self._anchor_brackets()

        report = self._merge("Spring Anchor Bracket", dry_run=True)

        self.assertEqual(report["state"], "rehearsed", report)
        self.assertEqual(report["variants"], 4, report)
        for name, tmpl in made.items():
            self.assertTrue(tmpl.active, "%s was left changed" % name)
            self.assertFalse(tmpl.attribute_line_ids, name)
            self.assertEqual(tmpl.name, name)
        self.assertFalse(
            self._survivor("Spring Anchor Bracket"),
            "the merged product was left behind by the rehearsal")

    def test_running_it_again_does_nothing(self):
        """A migration gets re-run. The second pass must recognise its own
        work rather than fold the merged product into itself."""
        self._anchor_brackets()

        self._merge("Spring Anchor Bracket")
        again = self._merge("Spring Anchor Bracket")

        self.assertEqual(again["state"], "already merged", again)
        self.assertEqual(len(self._live_variants("Spring Anchor Bracket")), 4)

    # --- the shop has to find its parts on both sides of the merge --------

    def _flag_angles(self):
        made = {}
        for size, price in (('5.9"', 9.1), ('6-3/8"', 9.22)):
            for colour in ("Black", "White"):
                name = "Flag Angle %s %s" % (size, colour)
                made[name] = self._product(name, price=price, stock=50.0)
        return made

    def test_a_prepared_track_finds_its_brackets_before_the_merge(self):
        """The lookup this change could break, proved on today's catalogue
        first - so a failure after the merge is the merge's fault and not a
        test that never worked."""
        made = self._jamb_brackets()

        found = self.env["sale.order"]._track_prep_bracket_product("12", "White")

        self.assertEqual(found, made["Jamb Bracket # 12 White"].product_variant_id)

    def test_a_prepared_track_still_finds_its_brackets_after_the_merge(self):
        """THE ONE THAT MATTERS. A bracket not found does not fail on its own:
        _track_prep_sync abandons the whole preparation, so the customer's
        prepared track quietly arrives with no brackets and no flag angle."""
        self._jamb_brackets()

        self._merge("Jamb Bracket")
        found = self.env["sale.order"]._track_prep_bracket_product("12", "White")

        self.assertTrue(found, "the brackets were lost in the merge")
        self.assertEqual(
            found,
            self._variant("Jamb Bracket", **{
                "Bracket Size": "#12", "Colour": "White"}),
        )

    def test_a_black_track_is_never_given_a_white_bracket(self):
        """The finish is matched as a whole word, and it has to go on being
        matched once it is a variant value rather than part of a name."""
        self._jamb_brackets()

        self._merge("Jamb Bracket")

        for colour in ("Black", "White"):
            found = self.env["sale.order"]._track_prep_bracket_product("16", colour)
            self.assertEqual(found._aa_chosen_colour(), colour)
            self.assertEqual(
                found.product_template_attribute_value_ids.filtered(
                    lambda v: v.attribute_id.name == "Bracket Size").name,
                "#16",
            )

    def test_the_flag_angle_survives_the_merge_and_does_not_wander(self):
        """Two sizes, both in the track's finish, and the old lookup picked
        5.9" by alphabet. After the merge both are one product and ordering by
        name separates nothing - so the pick has to be deliberate, and it has
        to be the SAME one every time."""
        made = self._flag_angles()
        before = self.env["sale.order"]._track_prep_flag_for_colour("Black")
        self.assertEqual(before, made['Flag Angle 5.9" Black'].product_variant_id)

        self._merge("Flag Angle")

        after = self.env["sale.order"]._track_prep_flag_for_colour("Black")
        self.assertTrue(after, "the flag angle was lost in the merge")
        self.assertEqual(after._aa_chosen_colour(), "Black")
        self.assertEqual(
            after.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_id.name == "Flag Angle Size").name,
            '5.9"',
            "the flag angle changed size in the merge",
        )
        # Asked again, and again: the same variant, not whichever the database
        # felt like returning.
        for _ in range(3):
            self.assertEqual(
                self.env["sale.order"]._track_prep_flag_for_colour("Black"), after)

    def test_the_choice_text_is_just_the_name_before_a_merge(self):
        """Everything above leans on _aa_choice_text reading the same on an
        unmerged catalogue, which is how one code path serves the database
        before the migration and after it."""
        made = self._jamb_brackets()
        plain = made["Jamb Bracket # 14 Black"].product_variant_id

        self.assertEqual(plain._aa_choice_text(), "Jamb Bracket # 14 Black")
        self.assertEqual(plain._aa_chosen_colour(), "")

        self._merge("Jamb Bracket")
        merged = self._variant("Jamb Bracket", **{
            "Bracket Size": "#14", "Colour": "Black"})

        # THE ORDER OF THE VALUES IS ODOO'S, not this table's: it sorts them by
        # the attribute's own sequence, so a colour (10) comes before a size
        # (30+) whichever way round the family lists them. Nothing here may
        # depend on that order - the readers are regexes over the whole text -
        # so the test does not either.
        self.assertEqual(
            sorted(merged._aa_choice_text().split()),
            sorted("Jamb Bracket #14 Black".split()),
        )
        self.assertEqual(merged._aa_chosen_colour(), "Black")

    # --- the migration, which is what will run on the owner's database ----

    def _migration(self):
        """The real migration script, loaded from where Odoo will load it."""
        import importlib.util
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations", "19.0.2.49.0", "post-migration.py",
        )
        spec = importlib.util.spec_from_file_location("aa_merge_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_migration_merges_the_families(self):
        """Run the actual script, not a copy of what it does."""
        self._anchor_brackets()
        self._hinges()

        self._migration().migrate(self.env.cr, "19.0.2.48.0")

        self.assertEqual(len(self._live_variants("Spring Anchor Bracket")), 4)
        self.assertEqual(len(self._live_variants("Hinge")), 21)

    def test_the_migration_does_nothing_on_a_fresh_database(self):
        """No version means a database being created, which has no catalogue
        to fold - and folding one that a demo install happened to create would
        be a surprise."""
        made = self._anchor_brackets()

        self._migration().migrate(self.env.cr, None)

        for name, tmpl in made.items():
            self.assertTrue(tmpl.active, name)
            self.assertFalse(tmpl.attribute_line_ids, name)

    def test_the_owner_can_hold_the_merge_from_the_settings(self):
        """A migration runs on Prod the moment he merges, so there has to be a
        way to call it off that does not need us."""
        made = self._anchor_brackets()
        self.env["ir.config_parameter"].sudo().set_param(
            "spring_engineering.variant_merge_hold", "1")

        self._migration().migrate(self.env.cr, "19.0.2.48.0")

        for name, tmpl in made.items():
            self.assertTrue(tmpl.active, "%s was merged despite the hold" % name)
            self.assertFalse(tmpl.attribute_line_ids, name)
        self.assertFalse(self._survivor("Spring Anchor Bracket"))

    # --- the awkward cases in the owner's real catalogue ------------------

    def test_a_product_standing_in_the_red_keeps_its_negative_count(self):
        """HIS CATALOGUE HAS NEGATIVES. "White Trims" stands at -2 and several
        cable products are below zero too. A merge that quietly rounded those
        up to nothing would hand him back stock he has already sold."""
        made = self._anchor_brackets()
        short = made["Spring Anchor Bracket LH White"].product_variant_id
        self._put(short, -5.0, self.stock)
        self.assertEqual(self._on_hand(short), -5.0, "the fixture is not negative")

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "merged", report)
        self.assertEqual(
            self._on_hand(self._variant(
                "Spring Anchor Bracket", Hand="LH", Colour="White")),
            -5.0,
            "a product in the red came out of the merge at nothing",
        )

    def test_the_merged_product_is_published_if_any_of_them_was(self):
        """The base is picked for its stock, not for being on the website. If
        the one the customers could see is folded into one that was never
        published, the part would vanish from the shop."""
        made = self._anchor_brackets()
        for name, tmpl in made.items():
            tmpl.is_published = (name == "Spring Anchor Bracket LH White")

        self._merge("Spring Anchor Bracket")

        self.assertTrue(
            self._survivor("Spring Anchor Bracket").is_published,
            "the part dropped off the website in the merge",
        )

    def test_nothing_published_stays_unpublished(self):
        """And the other way: a part the owner has deliberately kept off the
        website must not be published by being merged."""
        made = self._anchor_brackets()
        for tmpl in made.values():
            tmpl.is_published = False

        self._merge("Spring Anchor Bracket")

        self.assertFalse(self._survivor("Spring Anchor Bracket").is_published)

    def test_a_skipped_family_says_why_once(self):
        """The price plan is worked out twice - once to check, once to do - so
        a family that cannot be priced must not report the same problem
        twice over."""
        made = self._anchor_brackets()
        made["Spring Anchor Bracket LH White"].list_price = 8.50

        report = self._merge("Spring Anchor Bracket")

        priced = [p for p in report["problems"] if "cannot be priced" in p]
        self.assertEqual(len(priced), 1, report["problems"])

    def test_a_quoted_price_is_not_rewritten_by_the_merge(self):
        """A draft quotation is repointed at the variant that now holds the
        stock. Writing a product id on a line recomputes its price, and a
        price somebody has already been QUOTED - a discount, a hand-typed
        figure - must not move because we tidied the catalogue underneath it.
        """
        made = self._anchor_brackets()
        variant = made["Spring Anchor Bracket RH White"].product_variant_id
        partner = self.env["res.partner"].create({"name": "Quote Holder"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [(0, 0, {
                "product_id": variant.id,
                "product_uom_qty": 3,
                "price_unit": 4.25,      # agreed on the phone, not list
            })],
        })
        self.assertEqual(order.order_line.price_unit, 4.25)

        self._merge("Spring Anchor Bracket")

        self.assertEqual(
            order.order_line.price_unit, 4.25,
            "the merge rewrote a price the customer had been quoted",
        )
        self.assertEqual(order.order_line.product_uom_qty, 3)

    def test_a_vendor_price_follows_the_part_it_was_for(self):
        """A vendor line usually hangs off the TEMPLATE, so repointing by
        variant id misses it and it is stranded on an archived product: the
        reordering rule still fires and there is no price to buy at. Worse,
        the base's own line would be left applying to every colour."""
        made = self._anchor_brackets()
        vendor = self.env["res.partner"].create({"name": "Canimex Test"})
        for name, price in (("Spring Anchor Bracket RH Black", 3.01),
                            ("Spring Anchor Bracket LH White", 3.44)):
            self.env["product.supplierinfo"].create({
                "partner_id": vendor.id,
                "product_tmpl_id": made[name].id,
                "price": price,
            })

        self._merge("Spring Anchor Bracket")

        for hand, colour, price in (("RH", "Black", 3.01), ("LH", "White", 3.44)):
            variant = self._variant(
                "Spring Anchor Bracket", Hand=hand, Colour=colour)
            lines = self.env["product.supplierinfo"].search([
                ("product_id", "=", variant.id)])
            self.assertEqual(len(lines), 1, "%s %s lost its vendor price" % (hand, colour))
            self.assertAlmostEqual(lines.price, price, 2)

        # And nothing is left speaking for the whole product.
        survivor = self._survivor("Spring Anchor Bracket")
        loose = self.env["product.supplierinfo"].search([
            ("product_tmpl_id", "=", survivor.id), ("product_id", "=", False)])
        self.assertFalse(
            loose, "a vendor line is still priced for every colour at once")

    def test_the_merged_product_keeps_every_shop_category_it_was_in(self):
        made = self._anchor_brackets()
        hardware = self.env["product.public.category"].create({"name": "T Hardware"})
        brackets = self.env["product.public.category"].create({"name": "T Brackets"})
        made["Spring Anchor Bracket RH Black"].public_categ_ids = [(6, 0, hardware.ids)]
        made["Spring Anchor Bracket LH White"].public_categ_ids = [(6, 0, brackets.ids)]

        self._merge("Spring Anchor Bracket")

        self.assertEqual(
            set(self._survivor("Spring Anchor Bracket").public_categ_ids.ids),
            {hardware.id, brackets.id},
        )

    def test_a_lot_tracked_family_is_refused(self):
        """A quant carries its lot, and a lot belongs to one product, so the
        stock of a tracked product cannot be moved this way. Say so."""
        made = self._anchor_brackets()
        made["Spring Anchor Bracket LH Black"].tracking = "lot"

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "skipped", report)
        self.assertTrue(any("tracked" in p for p in report["problems"]), report)

    # --- what a code review turned up -------------------------------------

    def test_a_pricelist_rule_follows_the_exact_product_it_priced(self):
        """MONEY A CUSTOMER IS CHARGED. A rule names a product as a template
        with no variant, or as both. Moving only the variant leaves the
        base's rule applying to every colour and every other rule stranded on
        an archived template - a #16 bracket sold at the #10 rule's price."""
        made = self._jamb_brackets()
        pricelist = self.env["product.pricelist"].create({"name": "T Dealer"})
        for name, price in (("Jamb Bracket # 10 Black", 0.90),
                            ("Jamb Bracket # 16 White", 1.45)):
            self.env["product.pricelist.item"].create({
                "pricelist_id": pricelist.id,
                "applied_on": "1_product",
                "product_tmpl_id": made[name].id,
                "compute_price": "fixed",
                "fixed_price": price,
            })

        self._merge("Jamb Bracket")

        cheap = self._variant("Jamb Bracket", **{
            "Bracket Size": "#10", "Colour": "Black"})
        dear = self._variant("Jamb Bracket", **{
            "Bracket Size": "#16", "Colour": "White"})
        untouched = self._variant("Jamb Bracket", **{
            "Bracket Size": "#16", "Colour": "Black"})

        self.assertAlmostEqual(
            pricelist._get_product_price(cheap, 1.0), 0.90, 2)
        self.assertAlmostEqual(
            pricelist._get_product_price(dear, 1.0), 1.45, 2)
        # AND NOT APPLIED TO EVERYTHING: the #16 Black had no rule, so it must
        # still be its own price and not the #10 rule's 0.90.
        self.assertAlmostEqual(
            pricelist._get_product_price(untouched, 1.0), 1.91, 2)

    def test_a_bom_for_one_variant_keeps_its_template_in_step(self):
        """A BoM whose output is a variant names the variant AND its template.
        Move one without the other and _bom_find, which keys on the template,
        finds nothing: the merged part has no BoM and the old one is orphaned.
        """
        made = self._anchor_brackets()
        old = made["Spring Anchor Bracket LH Black"]
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": old.id,
            "product_id": old.product_variant_id.id,
            "type": "normal",
        })

        self._merge("Spring Anchor Bracket")

        want = self._variant("Spring Anchor Bracket", Hand="LH", Colour="Black")
        self.assertEqual(bom.product_id, want)
        self.assertEqual(bom.product_tmpl_id, want.product_tmpl_id)
        self.assertEqual(
            self.env["mrp.bom"]._bom_find(want)[want], bom,
            "the merged part cannot find its own BoM")

    def test_a_family_with_a_hole_in_it_is_refused(self):
        """Odoo builds a variant for every COMBINATION, so a family missing
        one would offer a priced bracket that was never stocked. Both
        docstrings promised this refusal; now it exists."""
        made = self._anchor_brackets()
        # the catalogue no longer has an RH White - somebody renamed it
        made["Spring Anchor Bracket RH White"].name = "Anchor RH White, retired"

        report = self._merge("Spring Anchor Bracket")

        self.assertEqual(report["state"], "skipped", report)
        for tmpl in made.values():
            self.assertFalse(tmpl.attribute_line_ids, tmpl.name)

    def test_a_customers_wish_follows_the_product(self):
        """The wishlist drops any wish whose product is unpublished, so a wish
        for one of the folded products would silently empty."""
        made = self._anchor_brackets()
        variant = made["Spring Anchor Bracket RH White"].product_variant_id
        partner = self.env["res.partner"].create({"name": "Wisher"})
        wish = self.env["product.wishlist"].create({
            "partner_id": partner.id,
            "product_id": variant.id,
            "website_id": self.env["website"].search([], limit=1).id,
        })

        self._merge("Spring Anchor Bracket")

        self.assertEqual(
            wish.product_id,
            self._variant("Spring Anchor Bracket", Hand="RH", Colour="White"),
        )

    def test_the_flag_angle_pick_is_alphabetical_before_a_merge(self):
        """The lookup this replaced ordered by NAME. Created in reverse order,
        an id-ordered pick would answer 6-3/8" where the old code answered
        5.9" - a different part, in the window between the deploy and the
        migration."""
        backwards = {}
        for size in ('6-3/8"', '5.9"'):          # deliberately out of order
            for colour in ("Black", "White"):
                name = "Flag Angle %s %s" % (size, colour)
                backwards[name] = self._product(name, price=9.1, stock=10.0)

        found = self.env["sale.order"]._track_prep_flag_for_colour("Black")

        self.assertEqual(found, backwards['Flag Angle 5.9" Black'].product_variant_id)

    def test_the_report_counts_an_already_merged_family_as_done(self):
        self._anchor_brackets()
        self._merge("Spring Anchor Bracket")

        reports = self.env["product.template"]._aa_merge_variant_families(
            dry_run=False, only=["Spring Anchor Bracket"])

        self.assertIn("1 of 1 families merged",
                      self.env["product.template"]._aa_merge_report(reports))

    # --- the flag angle size, now that the owner has said -----------------

    def test_a_prepared_track_takes_the_5_9_flag_angle(self):
        """Owner, 2026-10-22: "every track takes 5.9" currently, that other
        size is for other things". It was getting that by alphabet; now it is
        asked for by size, on both sides of the merge."""
        self._flag_angles()

        before = self.env["sale.order"]._track_prep_flag_for_colour("White")
        self.assertIn("5.9", before._aa_choice_text())

        self._merge("Flag Angle")
        after = self.env["sale.order"]._track_prep_flag_for_colour("White")

        self.assertEqual(
            after.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_id.name == "Flag Angle Size").name,
            '5.9"',
        )
        self.assertEqual(after._aa_chosen_colour(), "White")

    def test_the_other_size_is_never_sent_instead(self):
        """THE WHOLE POINT OF ASKING BY SIZE. If the 5.9" is missing, the
        6-3/8" is not a substitute - it is for other things - so nothing is
        returned and the preparation refuses itself and tells the customer to
        call. A wrong part that fits nothing is worse than an order we have to
        finish by hand."""
        for colour in ("Black", "White"):
            self._product("Flag Angle 6-3/8\" %s" % colour, price=9.22, stock=10.0)

        found = self.env["sale.order"]._track_prep_flag_for_colour("Black")

        self.assertFalse(found, "the wrong flag angle was substituted")

    def test_the_setting_still_answers_when_there_is_no_5_9(self):
        """The escape hatch stays: a catalogue with no 5.9" at all can still
        name the part in Settings."""
        other = self._product('Flag Angle 6-3/8" Black', price=9.22, stock=10.0)
        self.env["ir.config_parameter"].sudo().set_param(
            "spring_engineering.track_prep_flag_product_id",
            str(other.product_variant_id.id))

        self.assertEqual(
            self.env["sale.order"]._track_prep_flag_for_colour("Black"),
            other.product_variant_id,
        )

    def test_a_third_size_cannot_quietly_take_over(self):
        """The failure this guards against: a size added to the catalogue, or
        the attribute's values reordered, used to change which part every
        prepared track was sent."""
        self._flag_angles()
        self._product('Flag Angle 4-1/2" Black', price=8.0, stock=10.0)

        found = self.env["sale.order"]._track_prep_flag_for_colour("Black")

        self.assertIn("5.9", found._aa_choice_text())

    def test_a_flag_angle_that_names_no_size_is_still_used(self):
        """The tolerance this lookup has always had is for SPELLINGS, not for
        sizes: "Flag Angle - Black" does not state the wrong size, it states
        none, and refusing it would take the whole preparation down. The first
        draft of the 5.9" rule did exactly that."""
        plain = self._product("Flag Angle - Black", price=9.1, stock=10.0)

        self.assertEqual(
            self.env["sale.order"]._track_prep_flag_for_colour("Black"),
            plain.product_variant_id,
        )

    def test_a_stated_size_beats_an_unstated_one(self):
        """With both in the catalogue, the one that says 5.9" wins."""
        self._product("Flag Angle - Black", price=9.1, stock=10.0)
        self._product('Flag Angle 5.9" Black', price=9.1, stock=10.0)

        found = self.env["sale.order"]._track_prep_flag_for_colour("Black")

        self.assertIn("5.9", found._aa_choice_text())
