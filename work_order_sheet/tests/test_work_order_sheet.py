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

    def _category(self, name, parent=None):
        return self.env["product.category"].create({
            "name": name, "parent_id": parent.id if parent else False})

    def _product(self, name, code=False, category=None):
        values = {"name": name, "default_code": code, "type": "consu"}

        if category:
            values["categ_id"] = category.id

        return self.env["product.product"].create(values)

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
        self.assertIn("State", sheet)

class TestWorkOrderSheetCover(TestWorkOrderSheet):
    """A cover to read, and a page per station to hand out."""

    def _ft(self):
        """Feet, enabled if the database has it switched off.

        Most units ship archived, so a plain search finds nothing and the test
        quietly fell back to Units - which meant the cable's FOOTAGE, the whole
        point of collapsing those four moves into one, was never asserted at
        all. The test passed and the figure was untested.
        """
        feet = self.env["uom.uom"].with_context(active_test=False).search(
            [("name", "=", "ft")], limit=1)

        if feet and not feet.active:
            feet.active = True

        return feet

    def test_the_cover_says_who_what_and_when(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        picking = self._picking([(track, 2)], origin="S00003")
        picking.date_deadline = "2026-10-20 08:00:00"
        sheet = self._sheet(picking)
        self.assertIn("CUSTOMER", sheet)
        self.assertIn("A Customer", sheet)
        self.assertIn("Deadline", sheet)
        self.assertIn("10/20/2026", sheet)
        self.assertIn("EVERYTHING ON THIS ORDER", sheet)
        self.assertIn("S00003", sheet)
        self.assertIn(picking.name, sheet)

    def test_the_summary_lists_every_category_and_line(self):
        tracks = self._category("Tracks")
        drums = self._category("Drums & Shaft Parts")
        track = self._product('2" Vertical Track 76"', "VT", tracks)
        drum = self._product("Canimex D400-96 White", "CD", drums)
        sheet = self._sheet(self._picking([(track, 2), (drum, 1)]))
        self.assertIn("2 categories", sheet)
        self.assertIn("2 lines", sheet)
        self.assertIn("Category", sheet)

    def test_each_category_gets_its_own_page(self):
        """The cover is read once; the pages behind it are handed out.

        So each one repeats the order number and the deadline - a sheet on its
        own at a bench has to say what it belongs to.
        """
        track = self._product('2" Vertical Track 76"', "VT", self._category("Tracks"))
        drum = self._product("Canimex D400-96 White", "CD", self._category("Drums"))
        picking = self._picking([(track, 2), (drum, 1)], origin="S00009")
        rendered, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "work_order_sheet.report_work_order_sheet", picking.ids)

        if isinstance(rendered, bytes):
            rendered = rendered.decode()

        # one cover plus one page per station
        self.assertEqual(rendered.count('class="page"'), 3)
        text = visible_text(rendered)
        # the order number appears on the cover and on each station page
        self.assertGreaterEqual(text.count(picking.name), 3)
        self.assertGreaterEqual(text.count("S00009"), 3)

    def test_a_cable_is_one_line_not_four(self):
        """THE BUG: a cable is sold as a cable and picked as four moves.

        Reel, sleeve, thimble and stop all come off one cart line, and listing
        all four asks the floor to read a bill of materials to work out that
        somebody bought one cable. Grouped by the SALE LINE rather than by a
        list of part numbers, so a box of sleeves bought on its own still
        appears - it has a sale line of its own and nothing to group with.
        """
        cable = self._product('1/8" 7x19 Cable', "CABLE-18")
        reel = self._product('1/8" 7X19 GAC (500 FT REEL)', "9150000604")
        sleeve = self._product('1/8" Oval Sleeve', "9150000621")
        thimble = self._product('1/8" Thimble', "9150000633")
        stop = self._product('1/8" Aluminum Cable Stop', "9150000627")

        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": cable.id, "product_uom_qty": 1})

        picking = self._picking(
            [(reel, 17.5), (sleeve, 2), (thimble, 2), (stop, 2)])
        picking.move_ids.sale_line_id = sale_line.id
        feet = self._ft()
        picking.move_ids.filtered(
            lambda m: m.product_id == reel).product_uom = feet.id

        lines = picking._work_order_lines()
        self.assertEqual(len(lines), 1, "the cable printed as four parts")
        self.assertEqual(lines[0]["name"], '1/8" 7x19 Cable')
        self.assertEqual(lines[0]["parts"], 4)
        # THE FOOTAGE IS THE POINT. The sleeve, thimble and stop are counted in
        # Units; the reel is consumed in feet, and that figure is the length of
        # cable to cut. Collapsing the four without carrying it would lose the
        # only measurement on the line.
        self.assertTrue(feet, "this database has no feet unit to test with")
        # IN INCHES: stock counts the reel in feet, the bench works in inches.
        self.assertEqual(lines[0]["length"], '210"')

        sheet = self._sheet(picking)
        self.assertNotIn("Oval Sleeve", sheet)
        self.assertNotIn("Thimble", sheet)
        self.assertNotIn("Aluminum Cable Stop", sheet)

    def test_a_fitting_bought_on_its_own_still_appears(self):
        """The rule must not hide a box of sleeves somebody actually ordered."""
        sleeve = self._product('1/8" Oval Sleeve (100 pk)', "9150000621")
        sheet = self._sheet(self._picking([(sleeve, 3)]))
        self.assertIn("Oval Sleeve", sheet)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetKits(TestWorkOrderSheet):
    """A cable is summarised; a kit is not."""

    def _kit(self, parts, product_name="AA-1200 Hardware Kit"):
        kit = self._product(product_name, "AA-1200")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": kit.id, "product_uom_qty": 1})
        picking = self._picking(parts)
        picking.move_ids.sale_line_id = sale_line.id

        return kit, picking

    def test_a_kit_shows_every_part_that_has_to_be_picked(self):
        """THE CORRECTION: summarising a kit hides the work.

        A cable is a LENGTH CUT FROM STOCK and its reel, sleeve, thimble and
        stop are how one cable is made. A kit is a set of whole parts and every
        one of them comes off a shelf, so listing them is the point. Grouping
        on "one sale line, several moves" could not tell the two apart and
        hid both.
        """
        rollers = self._product("Nylon Roller 2in", "ROLL-2")
        hinges = self._product("Hinge #2", "HNG-2")
        bearing = self._product("End Bearing Plate", "EBP-1")
        kit, picking = self._kit([(rollers, 10), (hinges, 8), (bearing, 2)])

        lines = picking._work_order_lines()
        self.assertEqual(len(lines), 3, "the kit was summarised away")

        sheet = self._sheet(picking)
        for part in ["Nylon Roller 2in", "Hinge #2", "End Bearing Plate"]:
            self.assertIn(part, sheet, "the kit hid %s" % part)

    def test_a_cable_is_still_summarised(self):
        cable = self._product('1/8" 7x19 Cable', "CABLE-18")
        reel = self._product('1/8" 7X19 GAC (500 FT REEL)', "9150000604")
        sleeve = self._product('1/8" Oval Sleeve', "9150000621")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": cable.id, "product_uom_qty": 1})
        picking = self._picking([(reel, 17.5), (sleeve, 2)])
        picking.move_ids.sale_line_id = sale_line.id

        feet = self.env["uom.uom"].with_context(active_test=False).search(
            [("name", "=", "ft")], limit=1)
        feet.active = True
        picking.move_ids.filtered(
            lambda m: m.product_id == reel).product_uom = feet.id

        lines = picking._work_order_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["length"], '210"')
        self.assertNotIn("Oval Sleeve", self._sheet(picking))

    def test_a_cable_counted_in_units_is_still_summarised(self):
        """The name is a second signal, not a fallback nobody reaches.

        If the reel is counted in whole units rather than feet, the cut test
        says nothing - and the thing bought is still a cable, which is enough.
        """
        cable = self._product('5/32" 7x19 Cable', "CABLE-532")
        reel = self._product('5/32" 7X19 GAC Reel', "9150000608")
        stop = self._product('5/32" Aluminum Cable Stop', "9150000628")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": cable.id, "product_uom_qty": 1})
        picking = self._picking([(reel, 20), (stop, 2)])
        picking.move_ids.sale_line_id = sale_line.id

        self.assertEqual(len(picking._work_order_lines()), 1)

    def test_a_kit_and_a_cable_on_one_order(self):
        """Both rules at once, which is what a real order looks like."""
        roller = self._product("Nylon Roller 2in", "ROLL-2")
        hinge = self._product("Hinge #2", "HNG-2")
        kit, picking = self._kit([(roller, 10), (hinge, 8)])

        cable = self._product('1/8" 7x19 Cable', "CABLE-18")
        reel = self._product('1/8" 7X19 GAC (500 FT REEL)', "9150000604")
        sleeve = self._product('1/8" Oval Sleeve', "9150000621")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        cable_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": cable.id, "product_uom_qty": 1})

        for product, qty in [(reel, 17.5), (sleeve, 2)]:
            move = self.env["stock.move"].create({
                "picking_id": picking.id, "product_id": product.id,
                "product_uom_qty": qty, "product_uom": product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id})
            move.sale_line_id = cable_line.id

        sheet = self._sheet(picking)
        self.assertIn("Nylon Roller 2in", sheet, "the kit was summarised")
        self.assertIn("Hinge #2", sheet)
        self.assertIn('1/8" 7x19 Cable', sheet)
        self.assertNotIn("Oval Sleeve", sheet, "the cable was not summarised")


@tagged("post_install", "-at_install")


@tagged("post_install", "-at_install")
class TestWorkOrderSheetPages(TestWorkOrderSheet):
    """Four pages: Tracks, Springs, Cables, Hardware.

    The eCommerce tree has eleven categories and stays as it is for the
    website. This is how the FLOOR wants the work divided, and the two are
    allowed to differ.
    """

    def _shop_category(self, name, sequence=10):
        return self.env["product.public.category"].create({
            "name": name, "sequence": sequence})

    def _filed(self, name, code, category):
        return self.env["product.product"].create({
            "name": name, "default_code": code, "type": "consu",
            "public_categ_ids": [(6, 0, [category.id])]})

    def test_everything_else_is_swept_into_hardware(self):
        """Drums, Hinges, Rollers and the rest are one box, not six pages."""
        picking = self._picking([
            (self._filed("Canimex D400-96", "CD", self._shop_category("Drums")), 2),
            (self._filed("Hinge #2", "HG", self._shop_category("Hinges")), 8),
            (self._filed("Nylon Roller", "RL", self._shop_category("Rollers")), 10),
            (self._filed("Torsion Shaft", "SH", self._shop_category("Shafts")), 1),
        ])
        sheet = self._sheet(picking)
        self.assertIn("HARDWARE", sheet)
        for gone in ["DRUMS", "HINGES", "ROLLERS", "SHAFTS"]:
            self.assertNotIn(gone, sheet, "%s still has a page" % gone)

    def test_misc_is_hardware_now(self):
        picking = self._picking([
            (self._filed("Odd Part", "ODD", self._shop_category("Misc.")), 1)])
        sheet = self._sheet(picking)
        self.assertIn("HARDWARE", sheet)
        self.assertNotIn("MISC", sheet)

    def test_tracks_and_springs_keep_their_own_page(self):
        picking = self._picking([
            (self._filed('2" Vertical Track 76"', "VT", self._shop_category("Tracks")), 2),
            (self._filed("Torsion Spring 2in", "SP", self._shop_category("Springs")), 2),
        ])
        sheet = self._sheet(picking)
        self.assertIn("TRACKS", sheet)
        self.assertIn("SPRINGS", sheet)

    def test_a_cable_gets_a_page_with_no_category_to_file_it_under(self):
        """Cables exists only on this sheet - the shop has no such category.

        So it cannot be decided by where a product is filed, only by what the
        product is.
        """
        cable = self._filed(
            '1/8" 7x19 Cable 500ft Reel', "REEL", self._shop_category("Misc."))
        sheet = self._sheet(self._picking([(cable, 1)]))
        self.assertIn("CABLES", sheet)
        self.assertNotIn("HARDWARE", sheet)

    def test_an_unfiled_product_still_lands_somewhere_sensible(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        drum = self._product("Canimex D400-96 White")
        self.assertFalse(track.public_categ_ids)
        sheet = self._sheet(self._picking([(track, 2), (drum, 1)]))
        self.assertIn("TRACKS", sheet)
        self.assertIn("HARDWARE", sheet)

    def test_the_pages_are_always_in_the_same_order(self):
        picking = self._picking([
            (self._product("Canimex D400-96 White"), 1),
            (self._product('1/8" 7x19 Cable 500ft Reel'), 1),
            (self._product('2" Vertical Track 76"'), 2),
        ])
        sheet = self._sheet(picking)
        self.assertLess(sheet.index("TRACKS"), sheet.index("CABLES"))
        self.assertLess(sheet.index("CABLES"), sheet.index("HARDWARE"))

    def test_a_page_with_nothing_on_it_is_left_out(self):
        """An order of tracks alone is one page, not four with three empty."""
        sheet = self._sheet(self._picking([(self._product('2" Vertical Track 76"'), 2)]))
        self.assertIn("TRACKS", sheet)
        self.assertNotIn("CABLES", sheet)
        self.assertNotIn("HARDWARE", sheet)
        self.assertIn("1 categor", sheet)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetMeasurements(TestWorkOrderSheet):
    """The two measurements that were wrong on the floor's copy."""

    def test_a_horizontal_track_shows_its_length(self):
        """IT DID NOT, AND NOTHING SAID SO.

        The length was read from the number FOLLOWING the words "Vertical
        Track" or "Horizontal Track". That held for the vertical names and not
        for the horizontal ones, which print a blank column - and a blank reads
        like a product with no length rather than a rule that missed.
        """
        read = self.Picking._work_order_length
        self.assertEqual(read('[CH-HT-3"] 3" Horizontal Track - 96" Black'), '96"')
        self.assertEqual(read("CH-HT-2 Horizontal Track 96 black"), '96"')
        self.assertEqual(read('2" Horizontal Track 120" Long White'), '120"')

        # and on the sheet itself, not only in the helper
        product = self._product('[CH-HT-3"] 3" Horizontal Track - 96" Black', "HT")
        self.assertIn('96"', self._sheet(self._picking([(product, 2)])))

    def test_a_profile_and_a_door_height_are_not_lengths(self):
        read = self.Picking._work_order_length
        self.assertEqual(
            read('[CH-VT-2"] 2" Vertical Track 76" - 7\' Door Height Black'), '76"')
        self.assertEqual(
            read('[CH-VT-3"] 3" Vertical Track 100" - 9\' Door Height White'), '100"')

    def test_a_fractional_track_length_survives(self):
        self.assertEqual(
            self.Picking._work_order_length("Horizontal Track 96 1/2 Black"),
            '96 1/2"')

    def test_a_cable_is_measured_in_inches_not_feet(self):
        """THE REST OF THE SHEET IS IN INCHES.

        Stock counts the reel in feet and 17.5 ft is a stock figure; the person
        cutting it works to 210", the same units as every track length and
        every spring on the page.
        """
        cable = self._product('1/8" 7x19 Cable', "CABLE-18")
        reel = self._product('1/8" 7X19 GAC (500 FT REEL)', "9150000604")
        sleeve = self._product('1/8" Oval Sleeve', "9150000621")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": cable.id, "product_uom_qty": 1})
        picking = self._picking([(reel, 17.5), (sleeve, 2)])
        picking.move_ids.sale_line_id = sale_line.id
        feet = self.env["uom.uom"].with_context(active_test=False).search(
            [("name", "=", "ft")], limit=1)
        feet.active = True
        picking.move_ids.filtered(
            lambda m: m.product_id == reel).product_uom = feet.id

        lines = picking._work_order_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["length"], '210"')
        # NOT a bare "ft" search: the page's own stylesheet contains "left".
        self.assertNotIn("17.5 ft", self._sheet(picking))


@tagged("post_install", "-at_install")
class TestWorkOrderSheetDoor(TestWorkOrderSheet):
    """The door on every page header, and only what the customer gave."""

    FULL = ("Custom Torsion Spring Assembly\n"
            "Duplex, 2 springs\n"
            'Outer: 0.2625" wire, 6.0" ID, 32.25" long\n'
            "Door: 9' 0\" wide, 7' 0\" high, 355 lb, 12\" hi-lift, 25,000 cycles")
    NO_HILIFT = ("Custom Torsion Spring Assembly\n"
                 "Duplex, 2 springs\n"
                 'Outer: 0.2625" wire, 6.0" ID, 32.25" long\n'
                 "Door: 9' 0\" wide, 7' 0\" high, 355 lb, 25,000 cycles")
    OLD = ("Custom Torsion Spring Assembly\n"
           "Duplex, 2 springs\n"
           'Outer: 0.2625" wire, 6.0" ID, 32.25" long\n'
           "Door: 355 lb, 7' 0\", 25,000 cycles")

    def _with_spring(self, description, extra=()):
        product = self._product("Custom Torsion Spring Assembly", "SPRING-CUSTOM")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": product.id,
            "product_uom_qty": 1, "name": description})
        picking = self._picking([(product, 1)] + list(extra))
        picking.move_ids[0].sale_line_id = line.id

        return picking

    def test_the_header_carries_the_whole_door(self):
        sheet = self._sheet(self._with_spring(self.FULL))
        self.assertIn("9' 0\" x 7' 0\"", sheet)
        self.assertIn("355 lb", sheet)
        self.assertIn('12" hi-lift', sheet)

    def test_a_door_with_no_hi_lift_says_nothing_about_hi_lift(self):
        """NOT a zero. A zero is a number somebody has to interpret."""
        sheet = self._sheet(self._with_spring(self.NO_HILIFT))
        self.assertIn("9' 0\" x 7' 0\"", sheet)
        self.assertIn("355 lb", sheet)
        self.assertNotIn("hi-lift", sheet)

    def test_an_order_placed_before_width_existed_still_prints(self):
        """The old line carried weight, height and cycles and no width.

        Each fact is read on its own precisely so these keep working - matching
        the whole line would print nothing at all for them.
        """
        sheet = self._sheet(self._with_spring(self.OLD))
        self.assertIn("7' 0\" high", sheet)
        self.assertIn("355 lb", sheet)
        self.assertNotIn("wide", sheet)
        self.assertNotIn("hi-lift", sheet)

    def test_the_door_is_on_every_page_not_only_the_springs_one(self):
        """A track cutter is cutting for that same door."""
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        sheet = self._sheet(self._with_spring(self.FULL, extra=[(track, 2)]))
        self.assertIn("SPRINGS", sheet)
        self.assertIn("TRACKS", sheet)
        self.assertEqual(sheet.count("9' 0\" x 7' 0\""), 2,
                         "the door should head both pages")

    def test_an_order_with_no_spring_has_no_door_to_show(self):
        track = self._product('2" Vertical Track 76" - 7\' Door Height Black')
        sheet = self._sheet(self._picking([(track, 2)]))
        self.assertIn("TRACKS", sheet)
        self.assertNotIn("lb", sheet)
        self.assertNotIn("hi-lift", sheet)

    def test_the_spring_block_lists_them_too(self):
        sheet = self._sheet(self._with_spring(self.FULL))
        self.assertIn("Door width", sheet)
        self.assertIn("Door height", sheet)
        self.assertIn("Hi-lift", sheet)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetCablePage(TestWorkOrderSheet):
    """A cable is a cable wherever the shop files it."""

    def test_a_lift_cable_filed_under_tracks_still_prints_on_cables(self):
        """THE BUG: lift cables landed on the tracks page.

        The shop keeps them under the Tracks eCommerce category, and the
        category was read first. Cables is a page that exists only on this
        sheet, with no category of its own to be filed under, so what the
        product IS has to decide it - nothing else can.
        """
        tracks = self.env["product.public.category"].create({"name": "Tracks"})
        cable = self.env["product.product"].create({
            "name": '1/8" 7x19 Lift Cable', "default_code": "LC18",
            "type": "consu", "public_categ_ids": [(6, 0, [tracks.id])]})
        track = self.env["product.product"].create({
            "name": '2" Vertical Track 76"', "default_code": "VT",
            "type": "consu", "public_categ_ids": [(6, 0, [tracks.id])]})
        picking = self._picking([(cable, 2), (track, 2)])
        # ON THE STRUCTURE, not on a window of the rendered text. The cover
        # lists every line before the pages begin, so a search for a product
        # name in "the first 600 characters after TRACKS" reads into whatever
        # page follows it - which is how the first version of this test failed
        # against correct output.
        pages = {section["title"]: [line["name"] for line in section["lines"]]
                 for section in picking._work_order_sections()}

        self.assertIn('1/8" 7x19 Lift Cable', pages.get("Cables", []))
        self.assertNotIn('1/8" 7x19 Lift Cable', pages.get("Tracks", []))
        self.assertIn('2" Vertical Track 76"', pages.get("Tracks", []))


@tagged("post_install", "-at_install")
class TestWorkOrderSheetKitDoor(TestWorkOrderSheet):
    """A kit order records its door on the kit line, in its own shape."""

    # What aa_dealer_orders appends to the kit line's description.
    KIT_NOTE = ('AA-1200 Hardware Kit\n'
                'Track: 3" 15R | Lift: High Lift 12" | Drum: D400-96 | '
                'W 9\' 0" x H 7\' 0" | 300 lb')

    def _kit_order(self, note):
        kit = self._product("AA-1200 Hardware Kit", "AA-1200")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": kit.id,
            "product_uom_qty": 1, "name": note})
        picking = self._picking([(kit, 1)])
        picking.move_ids[0].sale_line_id = line.id

        return picking

    def test_a_kit_order_puts_its_door_on_the_header(self):
        """THE BUG: a kit ordered with a door specification showed none.

        The sheet looked for the door only in a spring assembly's description.
        A kit order has no spring to read - the dealer order writes the door
        onto the kit line instead, in a different shape.
        """
        sheet = self._sheet(self._kit_order(self.KIT_NOTE))
        self.assertIn("9' 0\" x 7' 0\"", sheet)
        self.assertIn("300 lb", sheet)
        self.assertIn('12" hi-lift', sheet)

    def test_a_kit_with_no_hi_lift_says_nothing_about_it(self):
        sheet = self._sheet(self._kit_order(
            'AA-1200 Hardware Kit\nTrack: 2" 12R | Lift: Standard | '
            'W 108" x H 84" | 250 lb'))
        self.assertIn('108" x 84"', sheet)
        self.assertIn("250 lb", sheet)
        self.assertNotIn("hi-lift", sheet)

    def test_a_kit_with_no_door_specification_shows_none(self):
        sheet = self._sheet(self._kit_order(
            'AA-1200 Hardware Kit\nTrack: 3" 15R | Lift: Standard'))
        self.assertIn("HARDWARE", sheet)
        self.assertNotIn(" lb", sheet)

    def test_a_spring_on_the_order_is_still_preferred(self):
        """The calculator's own figures beat a free-text note when both exist."""
        kit = self._product("AA-1200 Hardware Kit", "AA-1200")
        spring = self._product("Custom Torsion Spring Assembly", "SPRING-CUSTOM")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        kit_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": kit.id,
            "product_uom_qty": 1, "name": self.KIT_NOTE})
        spring_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": spring.id, "product_uom_qty": 1,
            "name": TestWorkOrderSheetDoor.FULL})
        picking = self._picking([(spring, 1), (kit, 1)])
        picking.move_ids.filtered(
            lambda m: m.product_id == spring).sale_line_id = spring_line.id
        picking.move_ids.filtered(
            lambda m: m.product_id == kit).sale_line_id = kit_line.id
        sheet = self._sheet(picking)
        self.assertIn("355 lb", sheet, "the spring's own figures should win")


@tagged("post_install", "-at_install")
class TestWorkOrderSheetCableNames(TestWorkOrderSheet):
    """This catalogue mostly does not use the word "cable"."""

    def test_the_catalogue_s_own_cable_names_are_recognised(self):
        """GAC is galvanized aircraft cable, and the reel never says "cable".

        Matching the word alone recognised none of these, so they fell through
        to their eCommerce category - which is Tracks - and printed on the
        tracks page.
        """
        kind = self.Picking._work_order_kind
        for name in ['1/8" 7X19 GAC (500 FT REEL)', '1/8" Oval Sleeve',
                     '1/8" Thimble', '1/8" Aluminum Cable Stop',
                     '5/32" 7x19 Cable 500ft Reel']:
            self.assertEqual(kind(name), "cable", "%r was not read as a cable" % name)

        self.assertEqual(kind('2" Vertical Track 76"'), "track")
        self.assertEqual(kind("Canimex D400-96 White"), "")

    def test_a_gac_reel_filed_under_tracks_prints_on_cables(self):
        tracks = self.env["product.public.category"].create({"name": "Tracks"})
        reel = self.env["product.product"].create({
            "name": '1/8" 7X19 GAC (500 FT REEL)', "default_code": "9150000604",
            "type": "consu", "public_categ_ids": [(6, 0, [tracks.id])]})
        picking = self._picking([(reel, 1)])
        pages = {s["title"]: [l["name"] for l in s["lines"]]
                 for s in picking._work_order_sections()}
        self.assertIn('1/8" 7X19 GAC (500 FT REEL)', pages.get("Cables", []))
        self.assertNotIn("Tracks", pages)

    def test_a_summarised_group_takes_its_kind_from_its_parts(self):
        """The thing SOLD may be named in a way this cannot read.

        Its components say plainly what it is - a GAC reel, an oval sleeve, a
        thimble - so a group that cannot name itself is read from them.
        """
        tracks = self.env["product.public.category"].create({"name": "Tracks"})
        sold = self.env["product.product"].create({
            "name": "1/8 Assembly 7 ft", "default_code": "ASM",
            "type": "consu", "public_categ_ids": [(6, 0, [tracks.id])]})
        reel = self._product('1/8" 7X19 GAC (500 FT REEL)', "9150000604")
        sleeve = self._product('1/8" Oval Sleeve', "9150000621")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": sold.id, "product_uom_qty": 1})
        picking = self._picking([(reel, 17.5), (sleeve, 2)])
        picking.move_ids.sale_line_id = sale_line.id

        pages = {s["title"]: [l["name"] for l in s["lines"]]
                 for s in picking._work_order_sections()}
        self.assertIn("1/8 Assembly 7 ft", pages.get("Cables", []))
        self.assertEqual(len(picking._work_order_lines()), 1,
                         "the parts should be summarised into the thing sold")

    def test_one_dimension_on_its_own_is_still_read(self):
        """The dealer form writes "W 9' 0\"" alone when only one is given.

        A pattern that required the pair found nothing at all in that case -
        which is why a door showed its weight and neither measurement.
        """
        read = self.Picking._work_order_dealer_door
        both = read('Track: 3" 15R | W 9\' 0" x H 7\' 0" | 300 lb')
        self.assertEqual(both["width"], "9' 0\"")
        self.assertEqual(both["height"], "7' 0\"")

        width_only = read('Track: 3" 15R | W 9\' 0" | 300 lb')
        self.assertEqual(width_only["width"], "9' 0\"")
        self.assertNotIn("height", width_only)

        height_only = read('Track: 3" 15R | H 7\' 0" | 300 lb')
        self.assertEqual(height_only["height"], "7' 0\"")
        self.assertNotIn("width", height_only)

    def test_the_spring_block_shows_the_width_when_there_is_one(self):
        product = self._product("Custom Torsion Spring Assembly", "SPRING-CUSTOM")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": product.id, "product_uom_qty": 1,
            "name": TestWorkOrderSheetDoor.FULL})
        picking = self._picking([(product, 1)])
        picking.move_ids[0].sale_line_id = line.id
        sheet = self._sheet(picking)
        self.assertIn("Door width", sheet)
        self.assertIn("9' 0\"", sheet)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetKitWithCable(TestWorkOrderSheet):
    def test_a_kit_containing_a_cable_is_still_a_kit(self):
        """EVERY part has to be a cable part, not merely one of them.

        A hardware kit that happens to contain a cable is still a kit, and
        summarising it would hide the rollers and hinges somebody has to pick.
        """
        kit = self._product("AA-1200 Hardware Kit", "AA-1200")
        roller = self._product("Nylon Roller 2in", "ROLL")
        hinge = self._product("Hinge #2", "HNG")
        reel = self._product('1/8" 7X19 GAC (500 FT REEL)', "9150000604")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": kit.id, "product_uom_qty": 1})
        picking = self._picking([(roller, 10), (hinge, 8), (reel, 1)])
        picking.move_ids.sale_line_id = sale_line.id

        names = [line["name"] for line in picking._work_order_lines()]
        self.assertEqual(len(names), 3, "the kit was summarised away")
        self.assertIn("Nylon Roller 2in", names)
        self.assertIn("Hinge #2", names)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetCableNamedForATrack(TestWorkOrderSheet):
    def test_a_cable_named_for_its_track_is_still_a_cable(self):
        """A cable is often named for the track or door it suits.

        A track is never named for a cable, so testing track first read every
        one of those as a track - and no amount of widening the cable pattern
        could fix it, because the cable pattern was never reached.
        """
        kind = self.Picking._work_order_kind
        for name in ['1/8" Lift Cable for 2in Track',
                     'Cable 7ft - 3in Track',
                     '7x19 GAC for 3in Track']:
            self.assertEqual(kind(name), "cable", "%r read as the wrong kind" % name)

        # and a track is still a track
        for name in ['2" Vertical Track 76" - 7\' Door Height Black',
                     "Horizontal Track 96 Black"]:
            self.assertEqual(kind(name), "track", "%r read as the wrong kind" % name)

    def test_such_a_cable_prints_on_the_cables_page(self):
        tracks = self.env["product.public.category"].create({"name": "Tracks"})
        cable = self.env["product.product"].create({
            "name": '1/8" Lift Cable for 2in Track', "default_code": "LC2",
            "type": "consu", "public_categ_ids": [(6, 0, [tracks.id])]})
        track = self.env["product.product"].create({
            "name": '2" Vertical Track 76"', "default_code": "VT",
            "type": "consu", "public_categ_ids": [(6, 0, [tracks.id])]})
        pages = {x["title"]: [l["name"] for l in x["lines"]]
                 for x in self._picking([(cable, 2), (track, 2)])._work_order_sections()}
        self.assertIn('1/8" Lift Cable for 2in Track', pages.get("Cables", []))
        self.assertIn('2" Vertical Track 76"', pages.get("Tracks", []))


@tagged("post_install", "-at_install")
class TestWorkOrderSheetDealerNoteEdges(TestWorkOrderSheet):
    """What a dealer note really looks like, including its warnings."""

    def test_a_spring_warning_is_not_the_door_weight(self):
        """THE BUG: the sheet showed 530 lb for a door that was not 530 lb.

        A warning is prose written after the door, and it repeats weights and
        drum ratings - "above 530 lb" and the like. It is cut off before the
        door is read rather than searched.
        """
        read = self.Picking._work_order_dealer_door
        facts = read('Track: 3" 15R | Lift: Standard | W 108" x H 84" | 300 lb'
                     ' | SPRING WARNING: doors above 530 lb need a bigger drum')
        self.assertEqual(facts["weight"], "300 lb")
        self.assertEqual(facts["width"], '108"')
        self.assertEqual(facts["height"], '84"')

    def test_a_line_that_is_not_a_dealer_note_gives_no_door(self):
        """A figure in pounds elsewhere is not the door's weight."""
        read = self.Picking._work_order_dealer_door
        self.assertEqual(read("Drum rated to 530 lb"), {})
        self.assertEqual(read("Some product 265 lb capacity"), {})

    def test_the_fullest_note_wins_not_the_first(self):
        """Several lines can carry a note.

        Returning the first that yielded anything let a line with only a weight
        beat the line that actually describes the door.
        """
        kit = self._product("AA-1200 Hardware Kit", "AA-1200")
        other = self._product("Some Extra", "EX")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        thin = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": other.id, "product_uom_qty": 1,
            "name": "Some Extra\nTrack: 3\" 15R | 530 lb"})
        full = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": kit.id, "product_uom_qty": 1,
            "name": 'AA-1200 Hardware Kit\nTrack: 3" 15R | Lift: High Lift 12" '
                    '| W 108" x H 84" | 300 lb'})
        picking = self._picking([(other, 1), (kit, 1)])
        picking.move_ids.filtered(
            lambda m: m.product_id == other).sale_line_id = thin.id
        picking.move_ids.filtered(
            lambda m: m.product_id == kit).sale_line_id = full.id

        door = picking._work_order_door()
        self.assertEqual(door["weight"], "300 lb")
        self.assertEqual(door["width"], '108"')
        self.assertEqual(door["height"], '84"')
        self.assertEqual(door["hilift"], '12"')

    def test_inches_from_the_dealer_form_reach_the_header(self):
        """The form collects inches, so the note carries 108\" and 84\"."""
        kit = self._product("AA-1200 Hardware Kit", "AA-1200")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": kit.id, "product_uom_qty": 1,
            "name": 'AA-1200 Hardware Kit\nTrack: 3" 15R | Lift: High Lift 12" '
                    '| W 108" x H 84" | 300 lb'})
        picking = self._picking([(kit, 1)])
        picking.move_ids[0].sale_line_id = line.id
        sheet = self._sheet(picking)
        self.assertIn('108" x 84"', sheet)
        self.assertIn("300 lb", sheet)
        self.assertIn('12" hi-lift', sheet)


@tagged("post_install", "-at_install")
class TestWorkOrderSheetThinNote(TestWorkOrderSheet):
    """A kit ordered without a track or a lift still describes its door."""

    def test_a_note_of_only_a_size_and_a_weight_is_still_a_door(self):
        """MY OWN REGRESSION. Requiring Track:, Lift: or Drum: was too strict.

        A kit ordered without a track or a lift has none of them, and its note
        is a size and a weight joined by pipes. That change took the weight off
        those sheets instead of correcting it - the opposite of the fix it was
        meant to be.
        """
        read = self.Picking._work_order_dealer_door
        facts = read('W 108" x H 84" | 300 lb')
        self.assertEqual(facts["width"], '108"')
        self.assertEqual(facts["height"], '84"')
        self.assertEqual(facts["weight"], "300 lb")

        weight_only = read("300 lb | something else")
        self.assertEqual(weight_only["weight"], "300 lb")

    def test_a_plain_product_description_is_still_not_a_door(self):
        """The pipe is the signal; a description does not contain one."""
        read = self.Picking._work_order_dealer_door
        self.assertEqual(read("Drum rated to 530 lb"), {})
        self.assertEqual(read("Some product 265 lb capacity"), {})

    def test_a_kit_spring_is_described_like_any_other(self):
        """A spring added as a kit option carries an extra line of its own.

        It is the same assembly described the same way, so it gets the same
        block - and its own page.
        """
        spring = self._product("Custom Torsion Spring Assembly", "SPRING-CUSTOM")
        kit = self._product("AA-1200 Hardware Kit", "AA-1200")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": spring.id, "product_uom_qty": 1,
            "name": TestWorkOrderSheetDoor.FULL + "\nSprings for the kit above"})
        picking = self._picking([(kit, 1), (spring, 1)])
        picking.move_ids.filtered(
            lambda m: m.product_id == spring).sale_line_id = line.id

        pages = {x["title"]: [l["name"] for l in x["lines"]]
                 for x in picking._work_order_sections()}
        self.assertIn("Springs", pages, "the kit's spring got no page")
        sheet = self._sheet(picking)
        self.assertIn("SPRING ASSEMBLY", sheet)
        self.assertIn("0.2625\"", sheet)
        self.assertIn("9' 0\" x 7' 0\"", sheet)

    def test_a_marker_below_the_first_row_is_still_found(self):
        read = self.Picking._work_order_spring
        product = self._product("Custom Torsion Spring Assembly", "SP")
        sale = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": sale.id, "product_id": product.id, "product_uom_qty": 1,
            "name": "Springs for the kit above\n" + TestWorkOrderSheetDoor.FULL})
        picking = self._picking([(product, 1)])
        picking.move_ids[0].sale_line_id = line.id
        self.assertTrue(read(picking.move_ids[0]),
                        "the assembly was not recognised below the first row")


@tagged("post_install", "-at_install")
class TestWorkOrderSheetUnmovedLines(TestWorkOrderSheet):
    """Ordered things that make no stock move still have to be made."""

    def _order_with(self, spring_type):
        spring = self.env.ref("spring_engineering.product_custom_spring")
        spring.type = spring_type
        kit = self.env["product.product"].create({
            "name": "AA-1200 Hardware Kit", "default_code": "AA-1200",
            "type": "consu", "is_storable": True})
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": kit.id, "product_uom_qty": 1,
            "name": 'AA-1200 Hardware Kit\nTrack: 3" 15R | W 108" x H 84" | 300 lb'})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": spring.product_variant_id.id,
            "product_uom_qty": 1,
            "name": TestWorkOrderSheetDoor.FULL + "\nSprings for the kit above"})
        order.action_confirm()

        return order.picking_ids[:1]

    def test_a_spring_that_moves_no_stock_is_still_on_the_sheet(self):
        """THE BUG BEHIND SEVERAL ROUNDS OF THE WRONG FIX.

        A custom assembly is made to order. If its product moves no stock -
        a service, for instance - Odoo puts no line on the transfer, so the
        sheet listed nothing: no Springs page, no specification, and no door,
        because the door is written on that very line. Every parsing fix was
        aimed at text that was not on the record at all.
        """
        picking = self._order_with("service")
        self.assertTrue(picking, "the order produced no transfer")
        self.assertNotIn(
            "Custom Torsion Spring Assembly",
            picking.move_ids.mapped("product_id.name"),
            "this test needs a product that makes no move")

        pages = {s["title"]: [l["name"] for l in s["lines"]]
                 for s in picking._work_order_sections()}
        self.assertIn("Springs", pages, "the assembly got no page")
        self.assertIn("Custom Torsion Spring Assembly", pages["Springs"])

        sheet = self._sheet(picking)
        self.assertIn("SPRING ASSEMBLY", sheet)
        self.assertIn('0.2625"', sheet)
        self.assertIn("9' 0\" x 7' 0\"", sheet)
        self.assertIn("355 lb", sheet)

    def test_it_says_made_to_order_rather_than_not_available(self):
        """It is not on a shelf and never will be.

        "Not available" would send somebody looking for it.
        """
        picking = self._order_with("service")
        springs = [s for s in picking._work_order_sections()
                   if s["title"] == "Springs"][0]
        self.assertEqual(springs["lines"][0]["availability"], "Made to order")

    def test_a_spring_that_does_move_stock_is_not_listed_twice(self):
        picking = self._order_with("consu")
        names = [l["name"] for l in picking._work_order_lines()]
        self.assertEqual(
            names.count("Custom Torsion Spring Assembly"), 1,
            "the assembly was listed both as a move and as an order line")
