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
            [("spring_assembly", "!=", False)], order="id desc", limit=1)

    def test_the_configured_assembly_is_stored_as_data(self):
        result = self._call(self._spec())
        self.assertNotIn("error", result, result)
        line = self._line()
        self.assertTrue(line, "no order line was created")
        self.assertEqual(line.spring_assembly, "Duplex")
        self.assertEqual(line.spring_count, 2)
        self.assertEqual(line.spring_door_weight, 355)
        self.assertEqual(line.spring_door_height, "7' 0\"")
        self.assertEqual(line.spring_cycles, 25000)
        self.assertTrue(line.spring_steel_weight > 0)

    def test_each_spring_keeps_its_own_wire_and_length(self):
        """An outer spring wound to the inner spring's wire is scrap."""
        self._call(self._spec())
        line = self._line()
        self.assertEqual(line.spring_a_role, "Outer")
        self.assertEqual(line.spring_a_wire, 0.2625)
        self.assertEqual(line.spring_a_id, 6)
        self.assertEqual(line.spring_a_length, 32.25)
        self.assertEqual(line.spring_b_role, "Inner")
        self.assertEqual(line.spring_b_wire, 0.2253)
        self.assertEqual(line.spring_b_id, 3.75)
        self.assertEqual(line.spring_b_length, 31.25)

    def test_a_single_spring_fills_one_slot_only(self):
        self._call(self._spec(
            assembly="Single", springs=1,
            springsSpec=[{"role": "Spring", "wire": 0.25, "id": 3.75,
                          "length": 28.0}]))
        line = self._line()
        self.assertEqual(line.spring_a_role, "Spring")
        self.assertFalse(line.spring_b_role)
        self.assertEqual(len(line.spring_detail_rows()), 1)

    def test_the_description_and_the_data_agree(self):
        """Two records of the same assembly must not drift apart.

        The description is what the customer reads and the fields are what the
        shop builds from; if they can disagree, one of them is a lie and
        nobody can tell which.
        """
        self._call(self._spec())
        line = self._line()
        self.assertIn("Duplex", line.name)
        self.assertIn('0.2625" wire', line.name)
        self.assertIn('32.25" long', line.name)
        self.assertEqual(line.spring_a_wire, 0.2625)
        self.assertEqual(line.spring_a_length, 32.25)

    def test_a_refused_spec_stores_nothing(self):
        before = self.env["sale.order.line"].search_count([])
        result = self._call(self._spec(springs=99))
        self.assertIn("error", result)
        self.assertEqual(self.env["sale.order.line"].search_count([]), before)
