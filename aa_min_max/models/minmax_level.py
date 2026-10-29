"""ONE ROW PER LINE OF HIS FILE, AND WHAT BECAME OF IT.

Owner, 2026-10-29, twice over: *"some items dont have a minimum set even
though you had the information"*, then *"there are still some products
missing, for example the flag angles."*

Both times the only way to answer was for me to go and read the file, and
both times the answer was different - once Odoo had deleted the rule, once
the row was never in the file at all. **He cannot tell those apart, and
neither could the screen**: both read "No Minimum Set".

So every line of the file is now a record, with what happened to it. The
Min / Max screen reads it and says which of three things is true of a part
with no minimum:

  * it is **not in the file** - nothing was ever given for it, so there is
    nothing to fix but to type one;
  * it **is in the file and could not be matched** - and the reason is right
    there, in words;
  * it was loaded and something has removed the rule since.

This is the same answer as Website > Configuration > Add-ons Check, and for
the same reason: answering "why do I not see it" by hand, twice, is the
signal to build the screen that answers it.
"""

from odoo import fields, models


class AaMinMaxLevel(models.Model):
    _name = "aa.minmax.level"
    _description = "Min / Max Level From File"
    _order = "state, code, name"

    code = fields.Char(string="Part #", index=True)
    name = fields.Char(string="Part", required=True)
    min_qty = fields.Float(string="Min", digits=(16, 2))
    max_qty = fields.Float(string="Max", digits=(16, 2))
    vendor = fields.Char(string="Vendor")
    product_id = fields.Many2one("product.product", string="Matched Part",
                                 ondelete="set null", index=True)
    state = fields.Selection([
        ("loaded", "Loaded"),
        ("unmatched", "Not Matched"),
    ], string="Result", default="unmatched", required=True, index=True)
    note = fields.Char(string="Why Not")
