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

    def _spec(self, **overrides):
        spec = {
            "assembly": "Duplex",
            "springs": 2,
            "springsSpec": [
                {"role": "Outer", "wire": 0.2625, "id": 6, "length": 32.25},
                {"role": "Inner", "wire": 0.2253, "id": 3.75, "length": 31.25},
            ],
            "doorWeight": 355,
            "doorHeight": "7' 0\"",
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
        self.assertRegex(
            rows[-1], r"""^Door: [\d,]+ lb, \d+' \d+", [\d,]+ cycles""")

    def test_both_springs_appear_with_their_own_figures(self):
        """An outer spring wound to the inner spring's wire is scrap."""
        self._call(self._spec())
        text = self._line().name
        # 6.0, not 6: the description formats these with Python's float
        # repr. Asserted as it really is, because a test written to the
        # format I assumed would have passed while the sheet showed nothing.
        self.assertIn('Outer: 0.2625" wire, 6.0" ID, 32.25" long', text)
        self.assertIn('Inner: 0.2253" wire, 3.75" ID, 31.25" long', text)

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
        self.assertIn("Door: 355 lb, 7' 0\", 25,000 cycles", self._line().name)

    def test_a_refused_spec_books_nothing(self):
        before = self.env["sale.order.line"].search_count([])
        result = self._call(self._spec(springs=99))
        self.assertIn("error", result)
        self.assertEqual(self.env["sale.order.line"].search_count([]), before)
