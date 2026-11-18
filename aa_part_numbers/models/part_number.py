"""AA Impact's own part numbers.

Owner, 2026-11-18, asked how he wanted them:

* "lo crearas tu y los pondras tu" - made and given here, not loaded from a
  list;
* "Por familia: AA-TRK-001" - a prefix per family of part;
* "las variantes de cada producto compartiran el numero de parte solo que al
  final habra una letra para diferenciarlos" - Hinge #1 Black and Hinge #1
  White are AA-HNG-002A and AA-HNG-002B;
* "Solo los de inventario" - stocked products only.

His standing rule (memory): the supplier's code stays in Internal Reference,
untouched, and AA's own reference goes in a separate field. So this is a
field of its own and `default_code` is never read or written.

A NUMBER NEVER CHANGES ONCE GIVEN. It is printed, written on boxes and said
on the telephone, so renaming a product or moving it to another category
leaves its number where it is. New products get the next free number of
their family; a new variant of an existing product gets the next free letter.

A product with ONE variant takes the bare number (AA-BLT-003). If it gains
variants later it keeps that number and the new ones take B, C... - the
letterless one stands for A.
"""

from odoo import api, fields, models

# The family is the product category. Three letters per family, written out
# rather than derived, because "Nuts & Bolts" -> "NUT" and "Misc." -> "MIS"
# are what a rule would make and nobody would say.
FAMILY_PREFIX = {
    'Tracks': 'TRK',
    'Hinges': 'HNG',
    'Springs': 'SPR',
    'Drums': 'DRM',
    'Rollers': 'RLR',
    'Shafts': 'SHF',
    'EBF': 'EBP',          # End Bearing Plates
    'Misc.': 'MSC',
    'Nuts & Bolts': 'BLT',
    'Motors': 'MTR',
    'Hardware Kits': 'KIT',
}
# His cable, sleeves, thimbles and cable stops carry no category at all.
CABLE_WORDS = ('gac', 'sleeve', 'thimble', 'cable')


def _letters(index):
    """0 -> A, 25 -> Z, 26 -> AA, 27 -> AB (Cut Down Hinge has 27)."""
    out = ''
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _letter_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # THE SUPPLIER'S NUMBER, SAID SO (owner, 2026-11-18: "quisiera mantener
    # el # de parte del proveedor como referencia" - kept, and labelled so
    # nobody mistakes it for ours). Only the label changes; the field, its
    # values and everything that reads it are Odoo's own.
    default_code = fields.Char(string='Supplier Part #')

    aa_part_base = fields.Char(
        string='AA Part #', copy=False, index=True, readonly=True,
        help="AA Impact's own part number. Variants share it and add a "
             "letter. Separate from the supplier's Internal Reference.")

    def write(self, vals):
        res = super().write(vals)
        # A product that starts being kept in stock, or is brought back from
        # the archive, gets its number then.
        if (vals.get('is_storable') or vals.get('active')) and self.product_variant_ids:
            self.product_variant_ids._aa_assign_part_numbers()
        return res

    @api.model
    def _aa_prefix(self, template):
        name = template.categ_id.name if template.categ_id else ''
        if name in FAMILY_PREFIX:
            return FAMILY_PREFIX[name]
        lower = (template.name or '').lower()
        if (not name or name in ('All', 'Goods', 'Saleable')) and \
                any(w in lower for w in CABLE_WORDS):
            return 'CBL'
        letters = ''.join(c for c in name.upper() if c.isalpha())
        return (letters[:3] or 'GEN').ljust(3, 'X')

    @api.model
    def _aa_next_base(self, prefix):
        stem = 'AA-%s-' % prefix
        # RAW SQL READS THE DATABASE, NOT THE ORM'S PENDING WRITES: without
        # this flush two products numbered in the same run get the same base.
        self.flush_model(['aa_part_base'])
        self.env.cr.execute(
            "SELECT aa_part_base FROM product_template WHERE aa_part_base LIKE %s",
            (stem + '%',))
        top = 0
        for (base,) in self.env.cr.fetchall():
            tail = base[len(stem):]
            if tail.isdigit():
                top = max(top, int(tail))
        return '%s%03d' % (stem, top + 1)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    default_code = fields.Char(string='Supplier Part #')

    aa_part_number = fields.Char(
        string='AA Part #', copy=False, index=True, readonly=True,
        help="AA Impact's own part number for this exact variant.")

    _aa_part_number_unique = models.Constraint(
        'UNIQUE(aa_part_number)', 'This AA part number is already in use.')

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        if products:
            products._aa_assign_part_numbers()
        return products

    def write(self, vals):
        res = super().write(vals)
        if vals.get('active'):
            self._aa_assign_part_numbers()
        return res

    def _aa_variant_key(self):
        values = self.product_template_attribute_value_ids
        return (tuple((v.attribute_id.sequence, v.attribute_id.id,
                       v.product_attribute_value_id.sequence,
                       v.product_attribute_value_id.id)
                      for v in values.sorted(lambda v: (v.attribute_id.sequence, v.attribute_id.id))),
                self.id)

    @api.model
    def _aa_assign_all(self):
        """Install: number every ACTIVE stocked product.

        NOT the archived ones. His database holds 111 archived templates -
        the products the catalogue merge of 2026-10-21 folded into variants -
        and numbering them put 111 gaps in the families before a single real
        part. An archived product gets its number if it is brought back."""
        self.sudo().search([])._aa_assign_part_numbers()

    def _aa_assign_part_numbers(self):
        """Number whichever of these stocked products has no number yet.

        Templates are taken in family then name order, so on the first run
        related parts sit together and the numbering reads sensibly.
        """
        Product = self.env['product.product'].sudo()
        products = self.sudo().filtered(
            lambda p: p.active and p.is_storable and not p.aa_part_number)
        if not products:
            return
        Template = self.env['product.template'].sudo()
        templates = products.mapped('product_tmpl_id').sorted(
            lambda t: (Template._aa_prefix(t), t.aa_part_base or '~', t.name or '', t.id))
        for template in templates:
            if not template.aa_part_base:
                template.aa_part_base = Template._aa_next_base(Template._aa_prefix(template))
            base = template.aa_part_base
            # Letters already given are reserved even on an archived variant,
            # so a number is never handed out twice.
            numbered = Product.with_context(active_test=False).search(
                [('product_tmpl_id', '=', template.id), ('aa_part_number', '!=', False)])
            siblings = Product.search([('product_tmpl_id', '=', template.id)])
            todo = (siblings - numbered).filtered('is_storable').sorted(
                lambda p: p._aa_variant_key())
            if not todo:
                continue
            if len(siblings) == 1 and not numbered:
                todo.aa_part_number = base
                continue
            used = set()
            for product in numbered:
                tail = product.aa_part_number[len(base):]
                # the letterless number of a once-single product stands for A
                used.add(_letter_index(tail) if tail.isalpha() else 0)
            index = 0
            for product in todo:
                while index in used:
                    index += 1
                product.aa_part_number = base + _letters(index)
                used.add(index)
