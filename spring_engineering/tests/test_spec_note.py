from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSpecNoteSurvives(TransactionCase):
    """A specification written onto an order line cannot be lost.

    `sale.order.line.name` is a stored COMPUTED field. Core rebuilds it from
    the product whenever product_id, linked_line_id or linked_line_ids changes,
    and a spring ordered as a kit option changes the last two the moment it is
    attached to its kit - so the entire specification was thrown away one line
    after it was written. It is kept in a field of its own now and put back on
    every recompute.
    """

    def setUp(self):
        super().setUp()
        self.order = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.res_partner_1").id,
        })
        self.product = self.env.ref("spring_engineering.product_custom_spring")
        self.line = self.env["sale.order.line"].create({
            "order_id": self.order.id,
            "product_id": self.product.product_variant_id.id,
            "product_uom_qty": 1,
        })

    def test_the_note_is_among_the_dependencies_of_the_description(self):
        """Which is what makes writing one enough to refresh the description.

        Odoo merges the dependencies declared by every override of a compute
        method, so core's are expected here too: a version that stopped merging
        them would break the recompute this fixes, silently, and this is where
        it would show.
        """
        field = self.env["sale.order.line"]._fields["name"]
        depends = set(self.env.registry.field_depends[field])

        for name in ("product_id", "linked_line_id", "linked_line_ids",
                     "aa_spec_note"):
            self.assertIn(name, depends)

    def test_writing_a_note_puts_it_on_the_description(self):
        self.line.aa_spec_note = 'Duplex, 2 springs\nOuter: 0.2625" wire'
        self.assertIn('Outer: 0.2625" wire', self.line.name or "")

    def test_a_recompute_does_not_lose_it(self):
        """THE BUG, reproduced at the level it happens on."""
        self.line.aa_spec_note = 'Duplex, 2 springs\nOuter: 0.2625" wire'
        self.line.invalidate_recordset()
        self.line.modified(["product_id"])
        self.line.flush_recordset()
        self.assertIn('Outer: 0.2625" wire', self.line.name or "")
        self.assertIn("Duplex, 2 springs", self.line.name or "")

    def test_it_is_written_once_however_often_the_description_is_rebuilt(self):
        self.line.aa_spec_note = "Duplex, 2 springs"

        for _ in range(3):
            self.line.invalidate_recordset()
            self.line.modified(["product_id"])
            self.line.flush_recordset()

        self.assertEqual((self.line.name or "").count("Duplex, 2 springs"), 1)

    def test_a_line_with_no_note_is_described_as_before(self):
        """Nothing changes for every other product in the catalogue."""
        self.assertFalse(self.line.aa_spec_note)
        self.assertIn("Custom Torsion Spring Assembly", self.line.name or "")

    def test_the_door_is_stored_as_numbers(self):
        self.line.aa_write_door({
            "width_in": 108, "height_in": 84, "weight_lb": 355,
            "hi_lift_in": 12, "cycles": "10,000"}, note="Duplex, 2 springs")
        self.assertEqual(self.line.aa_door_width_in, 108)
        self.assertEqual(self.line.aa_door_weight_lb, 355)
        self.assertEqual(self.line.aa_door_hi_lift_in, 12)
        self.assertEqual(self.line.aa_door_cycles, "10,000")
        self.assertIn("Duplex, 2 springs", self.line.name or "")
