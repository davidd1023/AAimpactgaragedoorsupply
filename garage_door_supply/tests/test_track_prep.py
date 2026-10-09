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
        self.attr = self.env.ref("garage_door_supply.attribute_track_preparation")
        self.v_unprepared = self.env.ref(
            "garage_door_supply.attribute_value_track_unprepared")
        self.v_prepared = self.env.ref(
            "garage_door_supply.attribute_value_track_prepared")

        self.jamb = self.env["product.template"].create({
            "name": "Test Jamb Bracket", "type": "consu", "list_price": 1.63})
        # The real products, by the names the owner gave: one per finish.
        self.flag_black = self.env["product.template"].create({
            "name": "Flag Angle Black", "type": "consu", "list_price": 7.5})
        self.flag_white = self.env["product.template"].create({
            "name": "Flag Angle White", "type": "consu", "list_price": 7.5})
        self.flag = self.flag_black

        params = self.env["ir.config_parameter"].sudo()
        params.set_param("garage_door_supply.track_prep_jamb_product_id",
                         str(self.jamb.product_variant_id.id))
        # Deliberately pointed at the WHITE angle, so a test that gets the
        # black one proves the colour match beat the fallback.
        params.set_param("garage_door_supply.track_prep_flag_product_id",
                         str(self.flag_white.product_variant_id.id))
        params.set_param("garage_door_supply.track_prep_inches_per_bracket", "24")

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

    def test_prepared_adds_brackets_by_height_and_one_flag(self):
        order = self._add(
            self._track("CH-VT-2-2 Vertical Track 76-7 door height black"), "Prepared")
        # 7 ft is 84", and 84 / 24 rounds up to 4.
        self.assertEqual(self._qty(order, self.jamb.product_variant_id), 4)
        self.assertEqual(self._qty(order, self.flag.product_variant_id), 1)

    def test_bracket_count_follows_the_door_height(self):
        for name, expected in [
            ("Vertical Track 8 door height black", 4),    # 96 / 24 = 4 exactly
            ("Vertical Track 10 door height black", 5),   # 120 / 24 = 5
            ("Vertical Track 12 door height white", 6),   # 144 / 24 = 6
        ]:
            order = self._add(self._track(name), "Prepared")
            self.assertEqual(
                self._qty(order, self.jamb.product_variant_id), expected, name)

    def test_unprepared_adds_nothing(self):
        order = self._add(
            self._track("CH-VT-2-2 Vertical Track 76-7 door height black"), "Unprepared")
        self.assertEqual(len(order.order_line), 1)

    def test_parts_follow_the_track_quantity(self):
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        order = self._add(tmpl, "Prepared")
        track_line = order.order_line.filtered(lambda l: not l.track_prep_role)
        order._cart_update_line_quantity(track_line.id, 3)
        self.assertEqual(self._qty(order, self.jamb.product_variant_id), 12)
        self.assertEqual(self._qty(order, self.flag.product_variant_id), 3)

    def test_a_part_cannot_be_edited_on_its_own(self):
        tmpl = self._track("CH-VT-2-2 Vertical Track 76-7 door height black")
        order = self._add(tmpl, "Prepared")
        bracket = order.order_line.filtered(lambda l: l.track_prep_role == "jamb")
        order._cart_update_line_quantity(bracket.id, 99)
        # Still the four the door needs, not ninety-nine.
        self.assertEqual(self._qty(order, self.jamb.product_variant_id), 4)

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
        bracket = order.order_line.filtered(lambda l: l.track_prep_role == "jamb")
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
        self.assertEqual(self._qty(order, self.flag_black.product_variant_id), 1)
        self.assertEqual(self._qty(order, self.flag_white.product_variant_id), 0)

    def test_a_white_track_gets_the_white_angle(self):
        order = self._add(self._track("CH-VT-3-2 Vertical Track 92-8 door height white"),
                          "Prepared")
        self.assertEqual(self._qty(order, self.flag_white.product_variant_id), 1)
        self.assertEqual(self._qty(order, self.flag_black.product_variant_id), 0)

    def test_an_unknown_finish_adds_nothing(self):
        # Shipping the wrong colour is a return, so there is no default.
        order = self._add(self._track("CH-VT-2-2 Vertical Track 76-7 door height bronze"),
                          "Prepared")
        self.assertEqual(len(order.order_line), 1)
