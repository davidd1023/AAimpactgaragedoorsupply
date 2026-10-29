"""A MINIMUM PER PART, AND ONE SCREEN SAYING WHAT IS UNDER IT.

Owner, 2026-10-29: *"make minimum and maximum of each item, same thing we did
for the spring in which we need to make a warning when an item is below its
minimum so that we can make a reorder of that product. I want you to show this
all in a new menu youll make in inventory, in the reporting tab."*

He sent the spreadsheet back with 157 minimums filled in and 98 left blank.
The tests that matter are not about arithmetic - they are about **matching his
rows to the right variant**, because since the catalogue merge a part number
belongs to a whole family and `CH1108` alone cannot tell eight jamb brackets
apart.
"""

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.aa_min_max.models.minmax_load import (
    LEVELS_FILE,
    flatten,
    load_levels,
    read_levels,
)


@tagged("post_install", "-at_install")
class MinMaxCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1)

    # --- fixtures mirroring his own catalogue ---------------------------------

    def a_part(self, name, code, on_hand=0.0):
        """A plain part, one variant, its own part number."""
        product = self.env["product.product"].create({
            "name": name, "default_code": code,
            "is_storable": True, "type": "consu"})

        if on_hand:
            self.env["stock.quant"]._update_available_quantity(
                product, self.warehouse.lot_stock_id, on_hand)

        return product

    def a_family(self, name, code, colours, sizes):
        """A MERGED FAMILY: one template, one part number, many variants.

        His jamb bracket is exactly this - `CH1108` on all eight of Black and
        White by #10 / #12 / #14 / #16 - and it is the shape that makes
        matching on the part number alone wrong.
        """
        colour = self.env["product.attribute"].create({
            "name": "Colour %s" % code, "create_variant": "always",
            "value_ids": [(0, 0, {"name": c}) for c in colours]})
        size = self.env["product.attribute"].create({
            "name": "Size %s" % code, "create_variant": "always",
            "value_ids": [(0, 0, {"name": s}) for s in sizes]})
        template = self.env["product.template"].create({
            "name": name, "default_code": code,
            "is_storable": True, "type": "consu",
            "attribute_line_ids": [
                (0, 0, {"attribute_id": colour.id,
                        "value_ids": [(6, 0, colour.value_ids.ids)]}),
                (0, 0, {"attribute_id": size.id,
                        "value_ids": [(6, 0, size.value_ids.ids)]}),
            ]})
        # THE PART NUMBER IS ON THE VARIANT, not the template - which is how
        # his merged catalogue actually holds it ("Part numbers are kept PER
        # VARIANT"). `product.template.default_code` is only a related field
        # and goes nowhere on a template with four variants, so a fixture that
        # set it there matched nothing and proved nothing.
        template.product_variant_ids.write({"default_code": code})

        return template

    def row(self, code, name, min_qty, max_qty=0.0, vendor=""):
        return {"code": code, "name": name, "min_qty": min_qty,
                "max_qty": max_qty, "vendor": vendor}

    def report(self, product):
        self.env.flush_all()
        self.env["aa.stock.minmax"].invalidate_model()
        rows = self.env["aa.stock.minmax"].search(
            [("product_id", "=", product.id)])

        self.assertEqual(len(rows), 1, "expected one report row for %s" % product.display_name)

        return rows

    def level(self, product):
        return self.env["stock.warehouse.orderpoint"].search(
            [("product_id", "=", product.id)], limit=1)

    # --- the file he sent back ------------------------------------------------

    def test_the_shipped_file_is_the_one_he_filled_in(self):
        """157 minimums, no maximum anywhere - *"the list doesn't currently
        show the max so we can just worry about the minimum for now."*"""
        rows = read_levels()

        self.assertEqual(len(rows), 157, LEVELS_FILE)
        self.assertTrue(all(r["min_qty"] > 0 for r in rows),
                        "a row with no minimum should not have been shipped")
        self.assertFalse([r for r in rows if r["max_qty"]],
                         "he left every maximum blank")
        # The shapes that make matching hard have to actually be in there.
        shared = [r for r in rows if r["code"] == "CH1108"]
        self.assertEqual(len(shared), 8, "the eight jamb brackets")

    def test_every_shipped_row_names_a_part(self):
        """The name is the only thing that tells a merged family apart, so a
        row without one could never be matched."""
        self.assertFalse([r for r in read_levels() if not r["name"]])

    # --- matching: the whole point --------------------------------------------

    def test_a_part_with_its_own_number_is_matched(self):
        part = self.a_part("Lag Screws", "LAG-TEST", on_hand=6000)

        load_levels(self.env, rows=[self.row("LAG-TEST", "Lag Screws", 9287)])

        self.assertAlmostEqual(self.level(part).product_min_qty, 9287, 2)

    def test_a_shared_part_number_goes_on_the_right_variant(self):
        """THE ONE THAT MATTERS. `CH1108` is all eight jamb brackets; his file
        gives each its own minimum. Matching on the number alone would have
        put one bracket's figure on all eight and looked like it worked."""
        template = self.a_family("Jamb Bracket", "CH1108-TEST",
                                 ["Black", "White"], ["#10", "#12"])
        rows = [
            self.row("CH1108-TEST", "Jamb Bracket (Black, #10)", 1152),
            self.row("CH1108-TEST", "Jamb Bracket (Black, #12)", 1391),
            self.row("CH1108-TEST", "Jamb Bracket (White, #10)", 288),
            self.row("CH1108-TEST", "Jamb Bracket (White, #12)", 348),
        ]

        load_levels(self.env, rows=rows)

        got = {}
        for variant in template.product_variant_ids:
            got[variant.display_name] = self.level(variant).product_min_qty

        for name, expected in (("Black, #10", 1152), ("Black, #12", 1391),
                               ("White, #10", 288), ("White, #12", 348)):
            match = [q for n, q in got.items() if name in n]

            self.assertEqual(len(match), 1, name)
            self.assertAlmostEqual(match[0], expected, 2,
                                   "%s got the wrong minimum" % name)

    def test_a_size_number_does_not_swallow_a_longer_one(self):
        """`Hinge (Black, #1)` flattens to a SUBSTRING of
        `Hinge (Black, #10)`, so a loose match would put the #1 minimum on the
        #10 part. His hinges stop at #9 and his jamb brackets start at #10, so
        nothing collides today - this is for the day one does."""
        # TWO COLOURS ON PURPOSE: Odoo leaves a single-value attribute OUT of
        # the variant name, so a one-colour fixture is named "Hinge (#1)" and
        # tests nothing about "(Black, #1)".
        template = self.a_family("Hinge", "CH1411-COLLIDE",
                                 ["Black", "White"], ["#1", "#10"])

        load_levels(self.env, rows=[
            self.row("CH1411-COLLIDE", "Hinge (Black, #1)", 274),
            self.row("CH1411-COLLIDE", "Hinge (Black, #10)", 999),
        ])

        got = {v.display_name: self.level(v).product_min_qty
               for v in template.product_variant_ids}
        one = [q for n, q in got.items() if n.endswith("Black, #1)")]
        ten = [q for n, q in got.items() if n.endswith("Black, #10)")]

        self.assertEqual(one, [274], "#1 took the wrong minimum")
        self.assertEqual(ten, [999], "#10 took the wrong minimum")

    def test_a_row_naming_no_known_variant_is_refused_not_guessed(self):
        """A minimum silently attached to the wrong variant is worse than one
        never loaded: the screen would call a part fine while the rack is
        empty."""
        template = self.a_family("Jamb Bracket", "CH1108-GUESS",
                                 ["Black", "White"], ["#10"])

        load_levels(self.env, rows=[
            self.row("CH1108-GUESS", "Jamb Bracket (Green, #10)", 999)])

        for variant in template.product_variant_ids:
            self.assertFalse(self.level(variant),
                             "a minimum was guessed onto %s" % variant.display_name)

    def test_a_part_number_nobody_has_is_refused(self):
        answer = load_levels(self.env, rows=[
            self.row("NO-SUCH-CODE", "Something", 100)])

        self.assertIn("could not be matched", answer["params"]["message"])
        self.assertIn("NO-SUCH-CODE", answer["params"]["message"])

    def test_what_it_refused_is_named_and_not_merely_counted(self):
        """"12 rows skipped" is not something anybody can act on."""
        answer = load_levels(self.env, rows=[
            self.row("MISSING-A", "A", 1), self.row("MISSING-B", "B", 2)])
        message = answer["params"]["message"]

        self.assertIn("MISSING-A", message)
        self.assertIn("MISSING-B", message)

    def test_punctuation_and_case_do_not_decide_a_match(self):
        """His file has been round a spreadsheet; a straight quote and a
        typographic one are the same bracket."""
        self.assertEqual(flatten('Torsion Spring Coil 2 5/8" (.243, L)'),
                         flatten("torsion spring coil 2 5/8” (.243, l)"))

    # --- re-running -----------------------------------------------------------

    def test_loading_twice_changes_nothing_the_second_time(self):
        part = self.a_part("Roller", "ROLL-TEST")
        rows = [self.row("ROLL-TEST", "Roller", 200)]
        load_levels(self.env, rows=rows)

        answer = load_levels(self.env, rows=rows)

        self.assertIn("1 already right", answer["params"]["message"])
        self.assertEqual(len(self.env["stock.warehouse.orderpoint"].search(
            [("product_id", "=", part.id)])), 1, "a second rule was created")

    def test_a_changed_minimum_is_written_over(self):
        part = self.a_part("Roller", "ROLL-EDIT")
        load_levels(self.env, rows=[self.row("ROLL-EDIT", "Roller", 200)])

        load_levels(self.env, rows=[self.row("ROLL-EDIT", "Roller", 350)])

        self.assertAlmostEqual(self.level(part).product_min_qty, 350, 2)

    # --- never order by itself ------------------------------------------------

    def test_the_rules_are_manual_and_never_automatic(self):
        """97 of the 157 parts are ALREADY below their minimum, so an `auto`
        rule would have sent a wall of purchase orders to four suppliers the
        night this was installed."""
        part = self.a_part("Hinge", "HINGE-TRIG")

        load_levels(self.env, rows=[self.row("HINGE-TRIG", "Hinge", 274)])

        self.assertEqual(self.level(part).trigger, "manual")

    # --- the screen -----------------------------------------------------------

    def test_a_part_under_its_minimum_reads_below_and_says_by_how_much(self):
        part = self.a_part("Lag Screws", "LAG-SHORT", on_hand=6000)
        load_levels(self.env, rows=[self.row("LAG-SHORT", "Lag Screws", 9287)])

        row = self.report(part)

        self.assertEqual(row.status, "below")
        self.assertAlmostEqual(row.on_hand, 6000, 2)
        self.assertAlmostEqual(row.min_qty, 9287, 2)
        self.assertAlmostEqual(row.short_by, 3287, 2)

    def test_exactly_at_the_minimum_counts_as_below(self):
        """HIS WORDS: *"Min = when you want the alert (when stock gets to this
        number or lower)."* His own Status column reads a part on 686.88
        against a minimum of 695 as BELOW MIN."""
        part = self.a_part("Roller", "ROLL-EQUAL", on_hand=200)
        load_levels(self.env, rows=[self.row("ROLL-EQUAL", "Roller", 200)])

        self.assertEqual(self.report(part).status, "below")

    def test_a_part_above_its_minimum_is_ok_and_short_by_nothing(self):
        part = self.a_part("Roller", "ROLL-OK", on_hand=800)
        load_levels(self.env, rows=[self.row("ROLL-OK", "Roller", 200)])

        row = self.report(part)

        self.assertEqual(row.status, "ok")
        self.assertAlmostEqual(row.short_by, 0, 2)

    def test_a_part_he_left_blank_is_untracked_and_never_below(self):
        """HIS RULE: *"Leave Min and Max blank for parts you don't want to
        track."* 98 rows came back blank. Reading a blank as nought would put
        every nut and bolt in the shop on the warning list."""
        part = self.a_part("Coil .289", "COIL-UNTRACKED", on_hand=45)

        row = self.report(part)

        self.assertEqual(row.status, "untracked")
        self.assertAlmostEqual(row.short_by, 0, 2)

    def test_stock_in_a_customer_location_is_not_ours(self):
        part = self.a_part("Roller", "ROLL-GONE", on_hand=500)
        load_levels(self.env, rows=[self.row("ROLL-GONE", "Roller", 200)])
        customers = self.env.ref("stock.stock_location_customers")
        self.env["stock.quant"]._update_available_quantity(part, customers, 900)

        self.assertAlmostEqual(self.report(part).on_hand, 500, 2,
                               "stock at a customer was counted as on hand")

    def test_the_maximum_column_exists_though_he_left_it_blank(self):
        """*"the list doesn't currently show the max so we can just worry
        about the minimum for now"* - so filling it in later is typing, not
        another deploy."""
        part = self.a_part("Roller", "ROLL-MAX")
        load_levels(self.env, rows=[
            self.row("ROLL-MAX", "Roller", 200, max_qty=800)])

        row = self.report(part)

        self.assertAlmostEqual(row.max_qty, 800, 2)
        self.assertAlmostEqual(self.level(part).product_max_qty, 800, 2)

    def test_a_blank_maximum_stays_blank_on_the_screen(self):
        """Odoo will not store a maximum under the minimum, so a blank one is
        written as the minimum itself - but showing that back would fill 157
        rows with a figure he never chose."""
        part = self.a_part("Roller", "ROLL-NOMAX")

        load_levels(self.env, rows=[self.row("ROLL-NOMAX", "Roller", 200)])

        self.assertFalse(self.report(part).max_qty)
        self.assertAlmostEqual(self.level(part).product_max_qty, 200, 2,
                               "Odoo's own constraint needs a maximum")

    # --- the vendor he already told me about ----------------------------------

    def test_his_vendor_is_put_on_a_part_that_has_none(self):
        """He gave a Vendor column; Odoo cannot raise a purchase order without
        one, and leaving it on the floor means asking him again later."""
        part = self.a_part("Coil", "COIL-VENDOR")

        load_levels(self.env, rows=[
            self.row("COIL-VENDOR", "Coil", 154, vendor="Iowa Spring")])

        self.assertEqual(part.seller_ids.partner_id.name, "Iowa Spring")

    def test_a_vendor_already_set_is_never_overwritten(self):
        """That is purchasing's own data, with prices and lead times behind
        it. A spreadsheet column is not grounds for touching it."""
        part = self.a_part("Coil", "COIL-KEEP")
        theirs = self.env["res.partner"].create({"name": "The Real Supplier"})
        self.env["product.supplierinfo"].create({
            "partner_id": theirs.id,
            "product_tmpl_id": part.product_tmpl_id.id, "price": 12.0})

        load_levels(self.env, rows=[
            self.row("COIL-KEEP", "Coil", 154, vendor="Iowa Spring")])

        self.assertEqual(part.seller_ids.partner_id, theirs)
        self.assertAlmostEqual(part.seller_ids.price, 12.0, 2)

    # --- where he asked for it ------------------------------------------------

    def test_the_menu_is_in_inventory_under_reporting(self):
        menu = self.env.ref("aa_min_max.menu_aa_stock_minmax")

        self.assertEqual(menu.parent_id,
                         self.env.ref("stock.menu_warehouse_report"))
        self.assertEqual(menu.action,
                         self.env.ref("aa_min_max.action_aa_stock_minmax"))

    def test_the_screen_opens_on_what_needs_ordering(self):
        action = self.env.ref("aa_min_max.action_aa_stock_minmax")

        self.assertIn("search_default_below", action.context)

    def test_a_row_can_open_its_own_levels_to_be_changed(self):
        """A report is a database view and cannot be typed into."""
        part = self.a_part("Roller", "ROLL-EDITBTN", on_hand=1)
        load_levels(self.env, rows=[self.row("ROLL-EDITBTN", "Roller", 200)])

        action = self.report(part).action_edit_levels()

        self.assertEqual(action["res_model"], "stock.warehouse.orderpoint")
        self.assertEqual(action["res_id"], self.level(part).id)

    def test_opening_the_levels_of_an_untracked_part_makes_a_rule_to_edit(self):
        part = self.a_part("Roller", "ROLL-NEWRULE")

        action = self.report(part).action_edit_levels()
        rule = self.env["stock.warehouse.orderpoint"].browse(action["res_id"])

        self.assertEqual(rule.product_id, part)
        self.assertEqual(rule.trigger, "manual")
        self.assertAlmostEqual(rule.product_min_qty, 0.0, 2)
