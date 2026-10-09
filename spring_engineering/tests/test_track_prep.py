from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTrackPreparation(TransactionCase):
    """A prepared vertical track must ship with the right parts, and they must
    stay right when the customer changes their mind.

    The quantities are the point. A prepared track with the wrong number of
    jamb brackets is worse than an unprepared one, because the customer does
    not find out until the installer is on the ladder.
    """

    def setUp(self):
        super().setUp()
        self.attr = self.env.ref("spring_engineering.attribute_track_preparation")
        self.v_unprepared = self.env.ref(
            "spring_engineering.attribute_value_track_unprepared")
        self.v_prepared = self.env.ref(
            "spring_engineering.attribute_value_track_prepared")

        # THE REAL CATALOGUE BRACKETS, not copies of them.
        #
        # garage_door_supply/data/arrow_products_data.xml already ships J-10 to
        # J-16 with these part numbers, and the lookup finds them by code. An
        # earlier version of this test created its own products with the same
        # codes and then asserted against those - the lookup quite correctly
        # returned the catalogue ones, so every bracket assertion saw zero.
        self.brackets = {}

        for size, code in [("10", "ATL-610J10JBBR"), ("12", "ATL-614J12JBBR"),
                           ("14", "ATL-616J14JBBR"), ("16", "ATL-616J16JBBR")]:
            found = self.env["product.product"].search(
                [("default_code", "=", code)], limit=1)
            self.assertTrue(found, "catalogue bracket %s is missing" % code)
            self.brackets[size] = found.product_tmpl_id
        # The flag angles, by the names the owner gave: one per finish.
        #
        # REUSED IF THEY EXIST, for the same reason as the brackets above. The
        # lookup finds a product by NAME, so a test that creates its own
        # "Flag Angle Black" alongside a real one asserts against the copy
        # while the code quite correctly uses the original - and every flag
        # assertion reads zero. That mistake was made twice in this file.
        def flag(name):
            found = self.env["product.product"].search(
                [("name", "=ilike", name)], limit=1)

            if found:
                return found.product_tmpl_id

            return self.env["product.template"].create({
                "name": name, "type": "consu", "list_price": 7.5})

        self.flag_black = flag("Flag Angle Black")
        self.flag_white = flag("Flag Angle White")
        self.flag = self.flag_black

        params = self.env["ir.config_parameter"].sudo()
        # Deliberately pointed at the WHITE angle, so a test that gets the
        # black one proves the colour match beat the fallback.
        params.set_param("spring_engineering.track_prep_flag_product_id",
                         str(self.flag_white.product_variant_id.id))

        self.partner = self.env["res.partner"].create({"name": "Test Buyer"})

    def _track(self, name):
        tmpl = self.env["product.template"].create({
            "name": name, "type": "consu", "list_price": 42.0})
        self.env["product.template.attribute.line"].create({
            "product_tmpl_id": tmpl.id, "attribute_id": self.attr.id,
            "value_ids": [(6, 0, [self.v_unprepared.id, self.v_prepared.id])]})
        tmpl.invalidate_recordset()

        return tmpl

    def _ptav(self, tmpl, name):
        return tmpl.attribute_line_ids.filtered(
            lambda l: l.attribute_id == self.attr
        ).product_template_value_ids.filtered(lambda p: p.name == name)

    def _add(self, tmpl, choice, qty=1):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        order._cart_add(
            tmpl.product_variant_id.id, qty,
            no_variant_attribute_value_ids=[self._ptav(tmpl, choice).id])

        return order

    def _qty(self, order, product):
        lines = order.order_line.filtered(lambda l: l.product_id == product)

        return sum(lines.mapped("product_uom_qty"))

    def test_prepared_adds_the_mix_and_two_flag_angles(self):
        order = self._add(
            self._track("CH-VT-2-2 Vertical Track 76-7 door height black"), "Prepared")
        self.assertEqual(self._qty(order, self.brackets["10"].product_variant_id), 4)
        self.assertEqual(self._qty(order, self.flag_black.product_variant_id), 2)
    def _mix(self, order):
        """{size: quantity} of brackets on this order."""
        out = {}

        for size, tmpl in self.brackets.items():
            qty = self._qty(order, tmpl.product_variant_id)

            if qty:
                out[size] = qty

        return out

    def test_the_mix_matches_the_owners_configurator(self):
        # The four readings, verbatim. These are the feature: a prepared pair
        # ships a graduated mix, not a count of one size.
        for name, expected in [
            ("Vertical Track 6 door height black", {"10": 4, "12": 4, "14": 4}),
            ("Vertical Track 7 door height black", {"10": 4, "12": 4, "14": 4}),
            ("Vertical Track 8 door height black", {"10": 4, "12": 5, "14": 5}),
            ("Vertical Track 9 door height white",
             {"10": 4, "12": 5, "14": 5, "16": 2}),
            ("Vertical Track 10 door height black",
             {"10": 4, "12": 5, "14": 5, "16": 4}),
        ]:
            order = self._add(self._track(name), "Prepared")
            self.assertEqual(self._mix(order), expected, name)

    def test_a_seven_foot_pair_is_two_of_each_per_track(self):
        # The owner's own description - "one vertical track might come with 2
        # brackets of 3 different sizes" - and 4/4/4 for the pair is exactly
        # that. This is the check that the per-pair reading is the right one.
        order = self._add(
            self._track("CH-VT-2-2 Vertical Track 76-7 door height black"), "Prepared")
        self.assertEqual(sum(self._mix(order).values()), 12)
        self.assertEqual(len(self._mix(order)), 3)

    def test_sixteens_appear_only_from_nine_feet(self):
        for name, has16 in [
            ("Vertical Track 8 door height black", False),
            ("Vertical Track 9 door height black", True),
        ]:
            order = self._add(self._track(name), "Prepared")
            self.assertEqual("16" in self._mix(order), has16, name)


    def test_unprepared_adds_nothing(self):
        order = self._add(
            self._track("CH-VT-2-2 Vertical Track 76-7 door height black"), "Unprepared")
        self.assertEqual(len(order.order_line), 1)

    def test_parts_follow_the_track_quantity(self):
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        order = self._add(tmpl, "Prepared")
        track_line = order.order_line.filtered(lambda l: not l.track_prep_role)
        order._cart_update_line_quantity(track_line.id, 2)
        # Two pairs is two doors: every size doubles, and so do the flags.
        self.assertEqual(self._mix(order), {"10": 8, "12": 8, "14": 8})
        self.assertEqual(self._qty(order, self.flag_black.product_variant_id), 4)

    def test_a_part_cannot_be_edited_on_its_own(self):
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        order = self._add(tmpl, "Prepared")
        bracket = order.order_line.filtered(lambda l: l.track_prep_role == "jamb_12")
        order._cart_update_line_quantity(bracket.id, 99)
        # Still the four the pair needs, not ninety-nine - and the OTHER sizes
        # are untouched, which a single shared role could not have managed.
        self.assertEqual(self._mix(order), {"10": 4, "12": 4, "14": 4})

    def test_removing_the_track_removes_its_parts(self):
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        order = self._add(tmpl, "Prepared")
        track_line = order.order_line.filtered(lambda l: not l.track_prep_role)
        order._cart_update_line_quantity(track_line.id, 0)
        self.assertFalse(order.order_line)

    def test_removing_a_part_removes_the_whole_prepared_track(self):
        # A prepared track minus its brackets is not something the owner sells,
        # so dropping the brackets drops the track rather than half-preparing it.
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        order = self._add(tmpl, "Prepared")
        bracket = order.order_line.filtered(lambda l: l.track_prep_role == "jamb_10")
        order._cart_update_line_quantity(bracket.id, 0)
        self.assertFalse(order.order_line)

    def test_an_unreadable_name_adds_nothing_and_warns(self):
        # Fail loudly: no height in the name means no guess at the bracket
        # count. Shipping the wrong number silently is the thing to avoid.
        tmpl = self._track("Mystery Vertical Track black")
        order = self._add(tmpl, "Prepared")
        self.assertEqual(len(order.order_line), 1)

    def test_the_switch_is_the_value_name(self):
        # models/sale_order.py matches on the text "Prepared" so that a value
        # added by hand on the live site works. If this value is ever renamed
        # the feature silently stops, so the name is asserted here.
        self.assertEqual(self.v_prepared.name, "Prepared")

    def test_the_flag_angle_matches_the_track_finish(self):
        # A black track must not ship a white angle. The setting points at the
        # white one, so finding the black one proves the colour match wins.
        order = self._add(self._track("CH-VT-2-2 Vertical Track 76-7 door height black"),
                          "Prepared")
        self.assertEqual(self._qty(order, self.flag_black.product_variant_id), 2)
        self.assertEqual(self._qty(order, self.flag_white.product_variant_id), 0)

    def test_a_white_track_gets_the_white_angle(self):
        order = self._add(self._track("CH-VT-3-2 Vertical Track 92-8 door height white"),
                          "Prepared")
        self.assertEqual(self._qty(order, self.flag_white.product_variant_id), 2)
        self.assertEqual(self._qty(order, self.flag_black.product_variant_id), 0)

    def test_an_unknown_finish_adds_nothing(self):
        # Shipping the wrong colour is a return, so there is no default.
        order = self._add(self._track("CH-VT-2-2 Vertical Track 76-7 door height bronze"),
                          "Prepared")
        self.assertEqual(len(order.order_line), 1)

    def test_a_height_off_the_table_adds_nothing(self):
        # #16 is still climbing at 10 ft, two more per foot, so 11 and 12 are
        # NOT extrapolated from four readings. They add nothing and say to call.
        for name in ["Vertical Track 11 door height black",
                     "Vertical Track 12 door height black",
                     "Vertical Track 14 door height black"]:
            order = self._add(self._track(name), "Prepared")
            self.assertEqual(len(order.order_line), 1, name)

    def test_the_option_is_attached_to_vertical_tracks_automatically(self):
        """The bug the owner hit: the attribute existed and was on nothing.

        Creating the attribute does not put it on a product, so the option
        appeared nowhere until each track was edited by hand. This asserts the
        attaching actually happens, for a track created WITHOUT it.
        """
        bare = self.env["product.template"].create({
            "name": "CH-VT-3-2 Vertical Track 100-9 door height white",
            "type": "consu", "list_price": 55.0})
        self.assertFalse(bare.attribute_line_ids.filtered(
            lambda l: l.attribute_id == self.attr))

        self.env["product.template"]._attach_track_preparation()
        bare.invalidate_recordset()

        line = bare.attribute_line_ids.filtered(lambda l: l.attribute_id == self.attr)
        self.assertTrue(line, "the option was not attached to a vertical track")
        self.assertEqual(
            sorted(line.value_ids.mapped("name")), ["Prepared", "Unprepared"])

    def test_attaching_twice_changes_nothing(self):
        # It runs on every module update, so it has to be idempotent.
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        before = len(tmpl.attribute_line_ids)
        self.env["product.template"]._attach_track_preparation()
        self.env["product.template"]._attach_track_preparation()
        tmpl.invalidate_recordset()
        self.assertEqual(len(tmpl.attribute_line_ids), before)

    def test_it_leaves_other_products_alone(self):
        # A horizontal track is not a vertical one and must not get the option.
        other = self.env["product.template"].create({
            "name": "CH-HT-2 Horizontal Track 96 black", "type": "consu"})
        self.env["product.template"]._attach_track_preparation()
        other.invalidate_recordset()
        self.assertFalse(other.attribute_line_ids.filtered(
            lambda l: l.attribute_id == self.attr))

    # The names as they actually are on the live site, prime marks and all.
    LIVE_NAMES = [
        ('[CH-VT-2"] 2" Vertical Track 76" - 7\' Door Height Black',
         {"10": 4, "12": 4, "14": 4}, "Black"),
        ('[CH-VT-3"] 3" Vertical Track 88" - 8\' Door Height White',
         {"10": 4, "12": 5, "14": 5}, "White"),
        ('[CH-VT-3"] 3" Vertical Track 100" - 9\' Door Height White',
         {"10": 4, "12": 5, "14": 5, "16": 2}, "White"),
        ('[CH-VT-2"] 2" Vertical Track 112" - 10\' Door Height Black',
         {"10": 4, "12": 5, "14": 5, "16": 4}, "Black"),
    ]

    def test_the_live_product_names_are_read_correctly(self):
        """The owner's real names, which the first pattern could not read.

        "... 76" - 7' Door Height Black" carries the height as 7' with a PRIME,
        and the original pattern allowed only ft/foot/feet - so every prepared
        track answered "we could not read the door height". The inch marks are
        why the first number in the name is the wrong one to take: 2" and 76"
        both come before the 7'.
        """
        for name, expected_mix, finish in self.LIVE_NAMES:
            order = self._add(self._track(name), "Prepared")
            self.assertEqual(self._mix(order), expected_mix, name)

            flag = self.flag_black if finish == "Black" else self.flag_white
            self.assertEqual(
                self._qty(order, flag.product_variant_id), 2,
                "wrong flag angle finish for %s" % name)

    def test_the_option_is_hidden_from_the_shop_filters(self):
        # It was appearing down the side of /shop under the categories, as if a
        # catalogue could be browsed by whether a track is prepared.
        self.assertEqual(self.attr.visibility, "hidden")

    def _owner_brackets(self):
        """The eight brackets as the owner names them, both finishes."""
        made = {}

        for finish in ("Black", "White"):
            for size in ("10", "12", "14", "16"):
                name = "Jamb Bracket # %s %s" % (size, finish)
                found = self.env["product.product"].search(
                    [("name", "=ilike", name)], limit=1)
                made[(size, finish)] = (
                    found.product_tmpl_id if found
                    else self.env["product.template"].create({
                        "name": name, "type": "consu", "list_price": 1.63})
                )

        return made

    def test_the_owners_bracket_names_are_found(self):
        """The failure the owner hit: three part numbers that exist nowhere.

        The brackets are stocked as "Jamb Bracket # 10 Black" - one per size
        per finish, eight in all - and the lookup was searching for catalogue
        part numbers and "J-10 Jamb Bracket". It found neither on the live site
        and refused every prepared track.
        """
        brackets = self._owner_brackets()
        order = self._add(
            self._track('[CH-VT-2"] 2" Vertical Track 76" - 7\' Door Height Black'),
            "Prepared")

        for size, qty in (("10", 4), ("12", 4), ("14", 4)):
            self.assertEqual(
                self._qty(order, brackets[(size, "Black")].product_variant_id), qty,
                "wrong quantity of Jamb Bracket # %s Black" % size)

    def test_the_brackets_match_the_track_finish(self):
        # A white track must not ship black brackets. Eight products exist and
        # only four of them belong on any given track.
        brackets = self._owner_brackets()
        order = self._add(
            self._track('[CH-VT-3"] 3" Vertical Track 88" - 8\' Door Height White'),
            "Prepared")

        self.assertEqual(
            self._qty(order, brackets[("12", "White")].product_variant_id), 5)
        self.assertEqual(
            self._qty(order, brackets[("12", "Black")].product_variant_id), 0,
            "a white track was given black brackets")

    def test_a_missing_bracket_is_named_the_way_the_owner_names_it(self):
        # The message has to be searchable in the back end. It previously
        # listed part numbers from a module the live site does not have.
        tmpl = self._track('2" Vertical Track 76" - 7\' Door Height Bronze')
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        warning = order._track_prep_sync(
            order.order_line[:1] or order.order_line)
        # Bronze is an unknown finish, so it stops before the brackets - the
        # point here is simply that no part number is quoted at a customer.
        self.assertNotIn("ATL-", warning or "")
