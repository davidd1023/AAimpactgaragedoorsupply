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
