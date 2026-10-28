import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSpringAddToCart(HttpCase):
    """The route the website calculator actually calls.

    Nothing covered it before this. The parameters the shop floor builds from
    are written here, and a field name mistyped in the controller would have
    raised at the moment a customer pressed Add To Cart - on the live site,
    with a full cart, and nowhere else.
    """

    def _call(self, spec):
        payload = {"jsonrpc": "2.0", "method": "call", "params": {"spec": spec}}
        response = self.url_open(
            "/spring-calculator/add-to-cart",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)

        return response.json().get("result", {})

    def _duplex(self, **overrides):
        """A nested pair - the thing the shop no longer winds."""
        spec = self._spec(
            assembly="Duplex",
            springsSpec=[
                {"role": "Outer", "wire": 0.2625, "id": 6, "length": 32.25},
                {"role": "Inner", "wire": 0.2253, "id": 3.75, "length": 31.25},
            ])
        spec.update(overrides)

        return spec

    def _spec(self, **overrides):
        # A SINGLE SPRING EACH SIDE, which is what this file used to call a
        # Duplex throughout. `springs` is how many are on the DOOR, a left and
        # a right; `springsSpec` is the NEST, one spring or an outer and an
        # inner. The default was the nest, and the nest is no longer sold
        # (owner, 2026-10-28), so every test here would have been testing the
        # refusal rather than what it was written for.
        spec = {
            "assembly": "Single",
            "springs": 2,
            "springsSpec": [
                {"role": "Spring", "wire": 0.2625, "id": 6, "length": 32.25},
            ],
            "doorWeight": 355,
            "doorHeight": "7' 0\"",
            "doorWidth": "9' 0\"",
            "hiLift": 0,
            "cycles": 25000,
        }
        spec.update(overrides)

        return spec

    def _line(self):
        return self.env["sale.order.line"].search(
            [("name", "like", "Custom Torsion Spring Assembly")],
            order="id desc", limit=1)

    def test_the_route_books_a_line(self):
        result = self._call(self._spec())
        self.assertNotIn("error", result, result)
        self.assertTrue(self._line(), "no order line was created")

    def test_the_description_keeps_the_shape_the_work_order_sheet_reads(self):
        """THE FORMAT IS AN INTERFACE, so it is pinned from this side too.

        There are deliberately no columns holding the specification a second
        time: the description IS the record, and work_order_sheet parses it to
        print the shop floor's copy. That makes this wording an interface
        rather than prose. If it changes, the sheet silently stops showing the
        assembly - so the shape is asserted here, where a change to it is made.
        """
        self._call(self._spec())
        rows = [r for r in self._line().name.splitlines() if r.strip()]
        self.assertEqual(rows[0].strip(), "Custom Torsion Spring Assembly")
        self.assertRegex(rows[1], r"^\w+, \d+ spring")
        self.assertRegex(
            rows[2], r'^\w+: [\d.]+" wire, [\d.]+" ID, [\d.]+" long')
        # The door line now leads with the size and carries a hi-lift when
        # there is one. The sheet reads each fact on its own rather than
        # matching the whole line, so this asserts the facts are present and
        # spelled the way it looks for - not their order.
        self.assertRegex(rows[-1], r"""^Door: .*\d+' \d+" wide""")
        self.assertRegex(rows[-1], r"""\d+' \d+" high""")
        self.assertRegex(rows[-1], r"[\d,]+ lb")
        self.assertRegex(rows[-1], r"[\d,]+ cycles")

    def test_the_spring_appears_with_its_own_figures(self):
        """A spring wound to the wrong wire is scrap, so the figures that
        reach the shop floor are pinned here."""
        self._call(self._spec())
        text = self._line().name
        # 6.0, not 6: the description formats these with Python's float
        # repr. Asserted as it really is, because a test written to the
        # format I assumed would have passed while the sheet showed nothing.
        self.assertIn('Spring: 0.2625" wire, 6.0" ID, 32.25" long', text)

    # --- DUPLEX IS NOT SOLD (owner, 2026-10-28) ---------------------------
    #
    # "for duplex springs we will leave the option there for people who want
    # to use it, but customers will no longer be able to add duplex springs
    # to the cart, instead give them a message on the page that will say
    # something like we do not currently manufacture custom duplex springs."

    def test_a_duplex_cannot_be_bought(self):
        """THE ONE THAT SETTLES IT. The page hides Add to Cart, but this
        route is public and takes a posted specification, so a hidden button
        stops nobody."""
        before = self.env["sale.order.line"].search_count([])
        result = self._call(self._duplex())

        self.assertIn("error", result, result)
        self.assertIn("do not currently manufacture", result["error"])
        self.assertIn("duplex", result["error"])
        self.assertEqual(self.env["sale.order.line"].search_count([]), before,
                         "a duplex booked a line anyway")

    def test_the_refusal_says_what_to_do_next(self):
        """A refusal with no way forward is a dead end, and this customer has
        a door that needs springs."""
        self.assertIn("786-238-7640", self._call(self._duplex())["error"])

    def test_a_single_spring_is_still_sold(self):
        """The ban is on the nest, not on the calculator or on springs."""
        self.assertNotIn("error", self._call(self._spec()))

    def test_a_single_spring_describes_one_spring(self):
        self._call(self._spec(
            assembly="Single", springs=1,
            springsSpec=[{"role": "Spring", "wire": 0.25, "id": 3.75,
                          "length": 28.0}]))
        rows = [r for r in self._line().name.splitlines() if r.strip()]
        self.assertIn("Single, 1 spring", rows[1])
        self.assertEqual(
            len([r for r in rows if '" wire,' in r]), 1,
            "a single assembly described more than one spring")

    def test_the_door_is_described(self):
        self._call(self._spec())
        self.assertIn(
            "Door: 9' 0\" wide, 7' 0\" high, 355 lb, 25,000 cycles",
            self._line().name)

    def test_a_refused_spec_books_nothing(self):
        before = self.env["sale.order.line"].search_count([])
        result = self._call(self._spec(springs=99))
        self.assertIn("error", result)
        self.assertEqual(self.env["sale.order.line"].search_count([]), before)

    def test_the_door_line_carries_width_and_hi_lift(self):
        """The work order sheet heads every page with the door.

        Width and hi-lift were known to the calculator and never sent, so the
        sheet could only ever show weight and height.
        """
        self._call(self._spec(hiLift=12))
        text = self._line().name
        self.assertIn('9\' 0" wide', text)
        self.assertIn('7\' 0" high', text)
        self.assertIn("355 lb", text)
        self.assertIn('12" hi-lift', text)

    def test_a_door_with_no_hi_lift_says_nothing_about_it(self):
        """A zero is a number somebody has to interpret; silence is not."""
        self._call(self._spec())
        text = self._line().name
        self.assertIn('9\' 0" wide', text)
        self.assertNotIn("hi-lift", text)

    def test_an_unreadable_width_does_not_stop_the_sale(self):
        """Neither width nor hi-lift touches the price, so neither may refuse.

        The line simply leaves off what it could not read.
        """
        result = self._call(self._spec(doorWidth="nonsense"))
        self.assertNotIn("error", result, result)
        text = self._line().name
        self.assertNotIn("wide", text)
        self.assertIn('7\' 0" high', text)
