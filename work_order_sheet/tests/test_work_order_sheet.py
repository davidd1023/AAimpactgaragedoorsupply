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
