import html
import re

from odoo.tests.common import TransactionCase, tagged


def visible_text(rendered):
    """The sheet as a person reads it: no tags, no entities, single spaces."""
    if isinstance(rendered, bytes):
        rendered = rendered.decode()

    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rendered)))


@tagged("post_install", "-at_install")
class TestWorkOrderSheet(TransactionCase):
    """What the shop floor is handed when an order reaches Work Orders."""

    def setUp(self):
        super().setUp()
        self.Picking = self.env["stock.picking"]
        self.picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "internal")], limit=1)
        self.partner = self.env["res.partner"].create({"name": "A Customer"})

    def _product(self, name, code=False):
        return self.env["product.product"].create({
            "name": name, "default_code": code, "type": "consu"})

    def _picking(self, products, origin="S00003"):
        picking = self.Picking.create({
            "picking_type_id": self.picking_type.id,
            "partner_id": self.partner.id,
            "origin": origin,
            "location_id": self.picking_type.default_location_src_id.id
                           or self.env.ref("stock.stock_location_stock").id,
            "location_dest_id": self.picking_type.default_location_dest_id.id
                                or self.env.ref("stock.stock_location_output").id,
        })

        for product, qty in products:
            self.env["stock.move"].create({
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            })

        return picking

    def _sheet(self, picking):
        rendered, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "work_order_sheet.report_work_order_sheet", picking.ids)

        return visible_text(rendered)

    # --- reading a length out of a name --------------------------------------

    def test_the_track_length_is_not_the_profile_or_the_door(self):
        """A track name carries THREE measurements and only one is the length.

            [CH-VT-2"] 2" Vertical Track 76" - 7' Door Height Black

        2" is the profile, 76" is what gets cut, 7' is the door it suits.
        Taking the first number in the name - the obvious implementation -
        cuts every track to two inches.
        """
        read = self.Picking._work_order_length
        self.assertEqual(
            read('[CH-VT-2"] 2" Vertical Track 76" - 7\' Door Height Black'), '76"')
        self.assertEqual(
            read('[CH-VT-3"] 3" Vertical Track 100" - 9\' Door Height White'), '100"')
        self.assertEqual(read("CH-HT-2 Horizontal Track 96 black"), '96"')

    def test_a_reel_is_not_a_length(self):
        """"500ft Reel" is a quantity of stock, not something to cut."""
        read = self.Picking._work_order_length
        self.assertEqual(read('1/8" 7x19 Cable 500ft Reel'), "")
        self.assertEqual(read('5/32" Cable Sleeve (100 pk)'), "")

    def test_a_product_with_no_length_says_nothing(self):
        read = self.Picking._work_order_length
        self.assertEqual(read("Canimex D400-96 White"), "")
        self.assertEqual(read("Jamb Bracket # 10 Black"), "")

    def test_what_kind_of_thing_each_line_is(self):
        kind = self.Picking._work_order_kind
        self.assertEqual(kind('2" Vertical Track 76" Black'), "track")
        self.assertEqual(kind('1/8" 7x19 Cable 500ft Reel'), "cable")
        self.assertEqual(kind("Canimex D400-96 White"), "")

    # --- the sheet ------------------------------------------------------------

    def test_every_product_is_on_the_sheet(self):
        """EVERY product, not only the ones this module understands.

        A sheet that silently drops the drum because it is neither a track nor
        a cable sends somebody to the shelf for half an order.
        """
        track = self._product(
            '2" Vertical Track 76" - 7\' Door Height Black', "CH-VT-2")
        drum = self._product("Canimex D400-96 White", "CH-CD02")
        reel = self._product('1/8" 7x19 Cable 500ft Reel', "ATL-9150000604")
        picking = self._picking([(track, 2), (drum, 1), (reel, 1)])
        sheet = self._sheet(picking)

        for wanted in ["CH-VT-2", "CH-CD02", "ATL-9150000604",
                       "Vertical Track", "Canimex D400-96", "7x19 Cable"]:
            self.assertIn(wanted, sheet, "the sheet omits %r" % wanted)

        self.assertIn('76"', sheet, "the track length is missing")
        self.assertIn("3 lines", sheet)

    def test_the_sheet_names_the_order_it_is_for(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        picking = self._picking([(track, 1)], origin="S00003")
        sheet = self._sheet(picking)
        self.assertIn("WORK ORDER", sheet)
        self.assertIn(picking.name, sheet)
        self.assertIn("S00003", sheet)
        self.assertIn("A Customer", sheet)

    def test_an_empty_work_order_says_so(self):
        picking = self._picking([])
        self.assertIn("nothing on this work order", self._sheet(picking))

    def test_the_sheet_is_plain_ascii(self):
        """wkhtmltopdf renders these as Latin-1 whatever the charset says.

        A non-breaking space prints as two characters of rubbish and an em dash
        as three. The rule is asserted rather than the symptom, so a curly
        quote pasted in next year fails here and not on paper.
        """
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        picking = self._picking([(track, 1)])
        rendered, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "work_order_sheet.report_work_order_sheet", picking.ids)

        if isinstance(rendered, bytes):
            rendered = rendered.decode()

        body = rendered[rendered.find("<main>"):]
        offenders = sorted({c for c in html.unescape(body) if ord(c) > 127})
        self.assertFalse(
            offenders, "characters wkhtmltopdf will mangle: %r" % offenders)

    def test_several_work_orders_print_as_several_sheets(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        first = self._picking([(track, 1)], origin="S00001")
        second = self._picking([(track, 2)], origin="S00002")
        rendered, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "work_order_sheet.report_work_order_sheet", (first | second).ids)

        if isinstance(rendered, bytes):
            rendered = rendered.decode()

        self.assertEqual(rendered.count('class="article"'), 2)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetSpring(TestWorkOrderSheet):
    """A configured assembly is not a catalogue item.

    Its order line reads "Custom Torsion Spring Assembly" and the thing that
    has to be wound is in the lines underneath it. Those lines ARE the record -
    there are deliberately no extra columns holding a second copy - so this
    reads them.
    """

    # The description spring_engineering writes, verbatim. If this ever stops
    # matching what that module produces, the block silently empties, which is
    # why its add-to-cart test asserts the same shape from the other side.
    DESCRIPTION = (
        "Custom Torsion Spring Assembly\n"
        "Duplex, 2 springs\n"
        'Outer: 0.2625" wire, 6" ID, 32.25" long\n'
        'Inner: 0.2253" wire, 3.75" ID, 31.25" long\n'
        "Door: 355 lb, 7' 0\", 25,000 cycles"
    )

    def _spring_line(self, description=None):
        product = self._product("Custom Torsion Spring Assembly", "SPRING-CUSTOM")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id,
            "product_id": product.id,
            "product_uom_qty": 1,
            "name": self.DESCRIPTION if description is None else description,
        })

        return product, line

    def _spring_picking(self, description=None, extra=()):
        product, line = self._spring_line(description)
        picking = self._picking([(product, 1)] + list(extra), origin="S00011")
        picking.move_ids[0].sale_line_id = line.id

        return picking

    def test_every_parameter_reaches_the_sheet(self):
        sheet = self._sheet(self._spring_picking())
        for wanted in ["SPRING ASSEMBLY", "Duplex", "Springs", "355 lb",
                       "7' 0\"", "25,000"]:
            self.assertIn(wanted, sheet, "the sheet omits %r" % wanted)

    def test_each_spring_is_listed_with_its_own_figures(self):
        """Wire, inside diameter and length, per position.

        An outer spring wound to the inner spring's wire is scrap, so the two
        rows must be complete and distinguishable rather than summarised.
        """
        sheet = self._sheet(self._spring_picking())
        self.assertIn("Outer", sheet)
        self.assertIn("Inner", sheet)
        # Lengths and inside diameters in EIGHTHS, wire in decimals. A tape
        # measure has no 32.25 on it, and a wire snapped to the nearest eighth
        # would read 1/4" - a different wire.
        for figure in ['0.2625"', '0.2253"', '6"', '3 3/4"', '32 1/4"',
                       '31 1/4"']:
            self.assertIn(figure, sheet, "missing %s" % figure)
        self.assertNotIn('3.75"', sheet, "an inside diameter printed as a decimal")
        self.assertNotIn('32.25"', sheet, "a length printed as a decimal")

    def test_a_single_spring_shows_one_row_not_two(self):
        picking = self._spring_picking(
            "Custom Torsion Spring Assembly\n"
            "Single, 1 spring\n"
            'Spring: 0.25" wire, 3.75" ID, 28" long\n'
            "Door: 180 lb, 7' 0\", 10,000 cycles")
        sheet = self._sheet(picking)
        self.assertIn("Single", sheet)
        self.assertIn("Spring", sheet)
        self.assertNotIn("Inner", sheet)

    def test_the_detail_survives_a_line_after_it(self):
        """THE CASE EVERY OTHER TEST HERE ONCE MISSED.

        The detail row was a sibling of the product loop rather than part of
        it, so it rendered once, after the loop, against the LAST line. An
        order of one spring printed it and every test passed; a real order - a
        spring followed by a track - lost it silently.
        """
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        sheet = self._sheet(self._spring_picking(extra=[(track, 2)]))
        self.assertIn("SPRING ASSEMBLY", sheet, "the spring detail was dropped")
        self.assertIn("Duplex", sheet)
        self.assertIn('0.2625"', sheet)
        self.assertIn('76"', sheet, "the track line lost its length")

    def test_an_ordinary_product_gets_no_spring_block(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        sheet = self._sheet(self._picking([(track, 2)]))
        self.assertNotIn("SPRING ASSEMBLY", sheet)
        self.assertIn('76"', sheet)

    def test_a_description_it_cannot_read_prints_no_block(self):
        """Half a specification is worse than none.

        An empty "SPRING ASSEMBLY" heading says the assembly has no
        specification. Saying nothing says the sheet does not know, which is
        true and sends somebody to look at the order.
        """
        for description in [
            "Custom Torsion Spring Assembly",
            "Custom Torsion Spring Assembly\nDuplex, 2 springs",
            "Custom Torsion Spring Assembly\nsomething else entirely",
        ]:
            sheet = self._sheet(self._spring_picking(description))
            self.assertNotIn(
                "SPRING ASSEMBLY", sheet,
                "a block was printed for %r" % description)

    def test_the_spring_detail_is_still_plain_ascii(self):
        rendered, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "work_order_sheet.report_work_order_sheet",
            self._spring_picking().ids)

        if isinstance(rendered, bytes):
            rendered = rendered.decode()

        body = rendered[rendered.find("<main>"):]
        offenders = sorted({c for c in html.unescape(body) if ord(c) > 127})
        self.assertFalse(offenders, "wkhtmltopdf will mangle: %r" % offenders)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetFloor(TestWorkOrderSheet):
    """The three things the floor asked for, and the grouping."""

    def test_measurements_read_like_a_tape_measure(self):
        read = self.Picking._work_order_inches
        self.assertEqual(read("32.25"), '32 1/4"')
        self.assertEqual(read("6.0"), '6"')
        self.assertEqual(read("3.75"), '3 3/4"')
        self.assertEqual(read("76"), '76"')
        self.assertEqual(read("0.125"), '0 1/8"')
        # 76.99 is a hair under 77 and must not read as a fraction of 76
        self.assertEqual(read("76.99"), '77"')

    def test_a_wire_size_keeps_its_decimals(self):
        """0.2625 snapped to the nearest eighth is 1/4 - a different wire.

        Wire is a decimal gauge, not a measurement off a tape, so it is the
        one figure on this sheet that must not be rounded to eighths.
        """
        self.assertEqual(
            self.Picking._work_order_inches("0.2625", fraction=False), '0.2625"')

    def test_a_track_length_is_shown_in_eighths_too(self):
        track = self._product('2" Vertical Track 76 1/2" - 7\' Door Height Black')
        sheet = self._sheet(self._picking([(track, 2)]))
        self.assertIn('76 1/2"', sheet)

    def test_the_sheet_says_what_is_not_on_the_shelf(self):
        """The order screen says Not Available and the paper used not to.

        A picker found out at the rack instead of at the printer.
        """
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        picking = self._picking([(track, 2)])
        picking.move_ids.write({"state": "confirmed"})
        sheet = self._sheet(picking)
        self.assertIn("Not available", sheet)
        self.assertIn("Stock", sheet, "the availability column is missing")

    def test_the_sheet_dates_itself(self):
        """A sheet on a bench is otherwise undateable."""
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        sheet = self._sheet(self._picking([(track, 1)]))
        self.assertIn("Printed", sheet)
        self.assertIn("Order state", sheet)

    def test_lines_are_grouped_by_station(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        reel = self._product('1/8" 7x19 Cable 500ft Reel')
        drum = self._product("Canimex D400-96 White")
        picking = self._picking([(drum, 1), (reel, 1), (track, 2)])
        sheet = self._sheet(picking)
        self.assertIn("TRACKS", sheet)
        self.assertIn("CABLES", sheet)
        self.assertIn("HARDWARE AND OTHER", sheet)
        # built in the order a door is built in, whatever order they were added
        self.assertLess(sheet.index("TRACKS"), sheet.index("CABLES"))
        self.assertLess(sheet.index("CABLES"), sheet.index("HARDWARE AND OTHER"))

    def test_an_order_of_one_kind_gets_one_heading(self):
        """Four headings for a tracks-only order would be noise."""
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        sheet = self._sheet(self._picking([(track, 2)]))
        self.assertIn("TRACKS", sheet)
        self.assertNotIn("CABLES", sheet)
        self.assertNotIn("HARDWARE AND OTHER", sheet)

    def test_the_springs_section_comes_first(self):
        spring_cls = TestWorkOrderSheetSpring
        product = self._product("Custom Torsion Spring Assembly", "SPRING-CUSTOM")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": product.id,
            "product_uom_qty": 1, "name": spring_cls.DESCRIPTION})
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        picking = self._picking([(track, 2), (product, 1)])
        picking.move_ids.filtered(
            lambda m: m.product_id == product).sale_line_id = line.id
        sheet = self._sheet(picking)
        self.assertLess(sheet.index("SPRINGS"), sheet.index("TRACKS"))
