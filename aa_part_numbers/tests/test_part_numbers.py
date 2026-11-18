from lxml import etree

from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval
from odoo.tests.common import TransactionCase

from ..models.part_number import _letters, _letter_index


@tagged('post_install', '-at_install')
class TestPartNumbers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Categ = cls.env['product.category']
        cls.hinges = Categ.create({'name': 'Hinges'})
        cls.bolts = Categ.create({'name': 'Nuts & Bolts'})
        Attr = cls.env['product.attribute']
        cls.color = Attr.create({'name': 'PN Color', 'sequence': 1, 'value_ids': [
            (0, 0, {'name': 'Black', 'sequence': 1}),
            (0, 0, {'name': 'White', 'sequence': 2})]})
        cls.size = Attr.create({'name': 'PN Size', 'sequence': 2, 'value_ids': [
            (0, 0, {'name': '#1', 'sequence': 1}),
            (0, 0, {'name': '#2', 'sequence': 2})]})

    def _template(self, name, categ, attrs=(), storable=True):
        return self.env['product.template'].create({
            'name': name, 'categ_id': categ.id if categ else False,
            'is_storable': storable, 'type': 'consu',
            'attribute_line_ids': [(0, 0, {
                'attribute_id': a.id, 'value_ids': [(6, 0, a.value_ids.ids)]})
                for a in attrs],
        })

    def test_variants_share_the_number_with_a_letter(self):
        """Owner: the variants share the part number with a letter at the end."""
        hinge = self._template('PN Hinge', self.hinges, (self.color, self.size))
        base = hinge.aa_part_base
        self.assertRegex(base, r'^AA-HNG-\d{3}$')
        numbers = {tuple(sorted(p.product_template_attribute_value_ids.mapped('name'))):
                   p.aa_part_number for p in hinge.product_variant_ids}
        # colour first (its attribute comes first), then size
        self.assertEqual(numbers[('#1', 'Black')], base + 'A')
        self.assertEqual(numbers[('#2', 'Black')], base + 'B')
        self.assertEqual(numbers[('#1', 'White')], base + 'C')
        self.assertEqual(numbers[('#2', 'White')], base + 'D')

    def test_a_single_product_takes_the_bare_number(self):
        nut = self._template('PN Hex Nut', self.bolts)
        self.assertRegex(nut.product_variant_id.aa_part_number, r'^AA-BLT-\d{3}$')
        self.assertEqual(nut.product_variant_id.aa_part_number, nut.aa_part_base)

    def test_the_next_product_of_a_family_takes_the_next_number(self):
        a = self._template('PN Nut A', self.bolts)
        b = self._template('PN Nut B', self.bolts)
        na = int(a.aa_part_base.rsplit('-', 1)[1])
        nb = int(b.aa_part_base.rsplit('-', 1)[1])
        self.assertEqual(nb, na + 1)

    def test_a_number_never_changes(self):
        nut = self._template('PN Stable Nut', self.bolts)
        number = nut.product_variant_id.aa_part_number
        nut.write({'name': 'PN Renamed Nut', 'categ_id': self.hinges.id})
        self.assertEqual(nut.product_variant_id.aa_part_number, number)

    def test_a_new_variant_takes_the_next_free_letter(self):
        hinge = self._template('PN Two Colour Hinge', self.hinges, (self.color,))
        before = set(hinge.product_variant_ids.mapped('aa_part_number'))
        self.assertEqual(before, {hinge.aa_part_base + 'A', hinge.aa_part_base + 'B'})
        grey = self.env['product.attribute.value'].create(
            {'name': 'Grey', 'attribute_id': self.color.id, 'sequence': 0})
        hinge.attribute_line_ids.write({'value_ids': [(4, grey.id)]})
        after = set(hinge.product_variant_ids.mapped('aa_part_number'))
        self.assertTrue(before <= after, 'existing numbers must not move')
        self.assertIn(hinge.aa_part_base + 'C', after)

    def test_not_stocked_gets_nothing_until_it_is(self):
        tmpl = self._template('PN Service Thing', self.bolts, storable=False)
        self.assertFalse(tmpl.aa_part_base)
        self.assertFalse(tmpl.product_variant_id.aa_part_number)
        tmpl.is_storable = True
        self.assertRegex(tmpl.product_variant_id.aa_part_number, r'^AA-BLT-\d{3}$')

    def test_uncategorised_cable_parts_are_cbl(self):
        # his cable parts sit in Odoo's catch-all category, or in none
        reel = self._template('PN 1/8" 7X19 GAC (500 FT REEL)',
                              self.env['product.category'].create({'name': 'All'}))
        self.assertTrue(reel.aa_part_base.startswith('AA-CBL-'))

    def test_the_supplier_reference_is_untouched(self):
        tmpl = self.env['product.template'].create({
            'name': 'PN Coded', 'categ_id': self.bolts.id, 'is_storable': True,
            'type': 'consu', 'default_code': 'CH1411-1'})
        self.assertEqual(tmpl.product_variant_id.default_code, 'CH1411-1')
        self.assertNotEqual(tmpl.product_variant_id.aa_part_number, 'CH1411-1')

    def test_numbers_are_unique_and_well_formed(self):
        self._template('PN Hinge X', self.hinges, (self.color, self.size))
        self._template('PN Hinge Y', self.hinges, (self.color, self.size))
        self.env['product.product']._aa_assign_all()
        numbers = self.env['product.product'].with_context(active_test=False).search(
            [('aa_part_number', '!=', False)]).mapped('aa_part_number')
        self.assertEqual(len(numbers), len(set(numbers)))
        for n in numbers:
            self.assertRegex(n, r'^AA-[A-Z]{3}-\d{3}[A-Z]*$')

    def test_letters_go_past_z(self):
        """Cut Down Hinge has 27 variants."""
        self.assertEqual([_letters(i) for i in (0, 25, 26, 27)], ['A', 'Z', 'AA', 'AB'])
        for i in range(60):
            self.assertEqual(_letter_index(_letters(i)), i)

    def test_typing_the_number_in_the_search_box_finds_it(self):
        """The box searches its FIRST field on Enter (the PO-number lesson)."""
        hinge = self._template('PN Searchable Hinge', self.hinges, (self.color,))
        number = hinge.product_variant_ids[0].aa_part_number
        arch = self.env['product.template'].get_views([(False, 'search')])['views']['search']['arch']
        first = etree.fromstring(arch).xpath('//field')[0]
        self.assertEqual(first.get('name'), 'name')
        domain = safe_eval(first.get('filter_domain'), {'self': number})
        self.assertIn(hinge, self.env['product.template'].search(domain))
