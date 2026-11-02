"""THE MODULE ON ITS OWN, which is the point of it.

`test_matches_the_original` proves the carve preserved the maths. These prove
the carved module is a WHOLE module - that it carries its own products, its
own pages and its own settings, and that nothing it needs was left behind in
`spring_engineering`.

These are the ones that still run on the second project, where there is no
original to compare against.
"""

from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.spring_calculator.controllers import main
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStandsAlone(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "A Customer"})

    def _spec(self, **overrides):
        """A single spring each side of a 9' x 7' door, 355 lb - the shop's
        commonest order, and the fixture the original's own tests use."""
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

    def _as_request(self):
        """`quote_assembly` and `add_assembly_lines` read the rates and the
        products off `request.env`, and want nothing else from a request."""
        return patch.object(main, "request", SimpleNamespace(env=self.env))

    # --- it carries its own products -----------------------------------------

    def test_the_spring_product_is_its_own(self):
        """Not borrowed from spring_engineering - that record will not exist
        on the second project."""
        product = self.env.ref("spring_calculator.product_custom_spring")

        self.assertTrue(product)
        self.assertEqual(product.name, "Custom Torsion Spring Assembly")

    def test_the_filler_product_is_its_own(self):
        self.assertTrue(self.env.ref("spring_calculator.product_custom_filler"))

    def test_the_spring_product_is_not_published(self):
        """Deliberate, and inherited from the original: it is not something
        to browse to, only something the calculator configures."""
        self.assertFalse(
            self.env.ref("spring_calculator.product_custom_spring").is_published)

    # --- it quotes -----------------------------------------------------------

    def test_it_quotes_a_door(self):
        with self._as_request():
            quote = main.quote_assembly(self._spec())

        self.assertNotIn("error", quote, quote)
        self.assertGreater(quote["assembly_total"], 0)
        self.assertIn("Custom Torsion Spring", quote["description"])

    def test_it_refuses_a_duplex(self):
        """The shop does not make them (owner, 2026-10-28) and the refusal
        has to travel with the calculator, not be left behind in the module
        that happened to hold the lock."""
        with self._as_request():
            quote = main.quote_assembly(self._spec(assembly="Duplex"))

        self.assertIn("error", quote)

    def test_the_rates_have_defaults(self):
        """A fresh database must be able to quote at all. The original ships
        these through a <function> call rather than records, and so does
        this - the reason is written down in the generated settings file."""
        params = self.env["ir.config_parameter"].sudo()

        self.assertTrue(params.get_param("spring_engineering.steel_per_lb"))
        self.assertTrue(params.get_param("spring_engineering.steel_cost_per_lb"))

    # --- it books a cart line ------------------------------------------------

    def test_it_books_a_spring_on_an_order(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})

        with self._as_request():
            quote = main.quote_assembly(self._spec())
            booked = main.add_assembly_lines(order, quote)

        self.assertNotIn("error", booked, booked)

        line = order.order_line.filtered(
            lambda l: l.product_id.product_tmpl_id
            == self.env.ref("spring_calculator.product_custom_spring"))

        self.assertTrue(line)
        self.assertGreater(line.price_unit, 0)

    def test_the_specification_is_stored_as_data(self):
        """`spring_spec_json` and the door figures are what a work order is
        built from downstream. The fields travel with the calculator; the
        track-prep half of the original's sale_order_line does not."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})

        with self._as_request():
            main.add_assembly_lines(order, main.quote_assembly(self._spec()))

        line = order.order_line[:1]

        self.assertTrue(line.spring_spec_json)
        self.assertEqual(line.aa_door_weight_lb, 355)
        self.assertTrue(line.aa_spec_note)

    def test_the_specification_survives_a_recompute(self):
        """The original's hard-won bug: `name` is a stored computed field and
        Odoo rebuilds it from the product, throwing the specification away.
        The fix is `aa_spec_note` plus the `_compute_name` override, and both
        had to come across or a spring would reach the floor with no wire,
        no length and no door."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})

        with self._as_request():
            main.add_assembly_lines(order, main.quote_assembly(self._spec()))

        line = order.order_line[:1]
        line.invalidate_recordset()
        line._compute_name()

        self.assertIn(line.aa_spec_note.strip().splitlines()[0], line.name)

    # --- it has its own pages ------------------------------------------------

    # Read as ARCH rather than rendered. Both pages `t-call="website.layout"`,
    # which needs a website request, and fetching them over HTTP cannot prove
    # anything HERE anyway: the two modules claim the same routes on purpose
    # (see the generator's header), so whichever answered would be a matter of
    # load order. On the second project, where the original does not exist,
    # the URLs are unambiguous.
    def test_the_calculator_page_mounts_its_own_component(self):
        """If this said `spring_engineering.calculator` the page would mount
        nothing at all on a project that has only this module."""
        arch = self.env.ref("spring_calculator.calculator_page").arch

        self.assertIn("spring_calculator.calculator", arch)
        self.assertNotIn("spring_engineering.calculator", arch)

    def test_the_custom_spring_page_exists_and_is_its_own(self):
        page = self.env.ref("spring_calculator.custom_torsion_spring_page")

        self.assertTrue(page.arch.strip())
        self.assertNotIn("spring_engineering.", page.arch)

    def test_the_backend_action_points_at_its_own_component(self):
        action = self.env.ref("spring_calculator.action_spring_calculator")

        self.assertEqual(action.tag, "spring_calculator.calculator")

    # --- and nothing it needs was left behind --------------------------------

    def test_it_does_not_depend_on_the_original(self):
        module = self.env["ir.module.module"].search(
            [("name", "=", "spring_calculator")], limit=1)

        self.assertNotIn(
            "spring_engineering",
            module.dependencies_id.mapped("name"),
            "the carved module must stand on its own - the second project"
            " will not have spring_engineering")
