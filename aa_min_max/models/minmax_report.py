"""EVERY PART, ITS MINIMUM, AND HOW FAR BELOW IT IS.

Owner, 2026-10-29: *"make minimum and maximum of each item ... we need to make
a warning when an item is below its minimum so that we can make a reorder of
that product. I want you to show this all in a new menu youll make in
inventory, in the reporting tab, so that way we can easily see the max and min
of each item. the list doesn't currently show the max so we can just worry
about the minimum for now."*

**THE LEVELS LIVE IN ODOO'S OWN REORDERING RULES**, not in two fields of ours.
That is the whole design decision. A minimum stock level is not a new idea -
`stock.warehouse.orderpoint` has held one since Odoo had inventory - and
putting his numbers there means the reorder he is heading towards is **Odoo's
Replenishment screen**, which counts incoming purchase orders, applies the
supplier's lead time and raises the order. A field of our own would have been
a second truth to keep in step, and would have had to be migrated into
reordering rules the day he wanted the purchase order.

So this model is a READ-ONLY VIEW over three things that already exist: the
products, their reordering rules, and the quants. It invents nothing.

**"SHORT BY" IS THE COLUMN THAT MAKES IT USABLE.** Ninety-seven of the 157
parts he set a minimum for are already below it, because the minimums cover
180 doors. A screen that opens with 97 red rows and no order to them is 97
rows of undifferentiated alarm; sorted by how far below, the top of it is the
list of what to ring the supplier about this morning.

**A PART WITH NO MINIMUM IS NOT A PROBLEM, IT IS UNTRACKED** - his own rule
from the spreadsheet: *"Leave Min and Max blank for parts you don't want to
track."* Ninety-eight rows came back blank and they are shown as Untracked,
never as below. Reading a blank as nought would have put every nut and bolt in
the shop on the warning list.
"""

from odoo import api, fields, models, tools


class AaStockMinMax(models.Model):
    _name = "aa.stock.minmax"
    _description = "Min / Max Stock Levels"
    _auto = False
    _order = "short_by desc, product_id"

    product_id = fields.Many2one("product.product", string="Part", readonly=True)
    code = fields.Char(string="Part #", readonly=True)
    categ_id = fields.Many2one("product.category", string="Category", readonly=True)
    uom_name = fields.Char(string="Unit", readonly=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor", readonly=True)

    on_hand = fields.Float(string="On Hand", readonly=True, digits=(16, 2))
    min_qty = fields.Float(string="Min", readonly=True, digits=(16, 2))
    max_qty = fields.Float(string="Max", readonly=True, digits=(16, 2))
    short_by = fields.Float(
        string="Short By", readonly=True, digits=(16, 2),
        help="How far under the minimum this part is. Nought when it is at or "
             "above the minimum, so sorting on it puts what needs ordering "
             "first.")
    status = fields.Selection([
        ("below", "Below Minimum"),
        ("ok", "OK"),
        ("unmatched", "In Your File - Not Matched"),
        ("untracked", "No Minimum Set"),
    ], string="Status", readonly=True)
    why = fields.Char(
        string="Why No Minimum", readonly=True,
        help="For a part with no minimum: whether a figure was ever given "
             "for it, and if one was, why it could not be placed.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
            WITH on_hand AS (
                -- INTERNAL LOCATIONS ONLY, so stock sitting in a customer or
                -- supplier location is not counted as ours.
                SELECT q.product_id, SUM(q.quantity) AS qty
                  FROM stock_quant q
                  JOIN stock_location l ON l.id = q.location_id
                 WHERE l.usage = 'internal'
                 GROUP BY q.product_id
            ), levels AS (
                -- SUMMED ACROSS RULES. One rule per part per warehouse is the
                -- normal case and sums to itself; a second warehouse later
                -- adds to the figure rather than being silently ignored.
                SELECT op.product_id,
                       SUM(op.product_min_qty) AS min_qty,
                       SUM(op.product_max_qty) AS max_qty
                  FROM stock_warehouse_orderpoint op
                 WHERE op.active
                 GROUP BY op.product_id
            ), from_file AS (
                -- WHAT HIS FILE SAID ABOUT THIS PART, matched or not. A part
                -- with no minimum is one of two completely different things -
                -- nothing was ever given for it, or something was and could
                -- not be placed - and the screen used to say the same words
                -- for both.
                SELECT DISTINCT ON (code) code, state, note
                  FROM aa_minmax_level
                 WHERE code IS NOT NULL AND code != ''
                 ORDER BY code, (state = 'loaded') DESC, id
            ), vend AS (
                -- The first vendor on the part, by the sequence the purchase
                -- module already orders them in - so this agrees with whoever
                -- Odoo would actually buy from.
                SELECT DISTINCT ON (si.product_tmpl_id)
                       si.product_tmpl_id, si.partner_id
                  FROM product_supplierinfo si
                 ORDER BY si.product_tmpl_id, si.sequence, si.id
            )
            SELECT pp.id AS id,
                   pp.id AS product_id,
                   pp.default_code AS code,
                   pt.categ_id,
                   uom.name->>'en_US' AS uom_name,
                   v.partner_id AS vendor_id,
                   COALESCE(oh.qty, 0) AS on_hand,
                   l.min_qty,
                   -- BLANK WHERE HE LEFT IT BLANK. Odoo will not store a
                   -- maximum below the minimum, so a blank one was written as
                   -- the minimum itself; showing that back would be 157 rows
                   -- of a figure he never chose.
                   NULLIF(l.max_qty, l.min_qty) AS max_qty,
                   CASE WHEN COALESCE(l.min_qty, 0) > 0
                        THEN GREATEST(l.min_qty - COALESCE(oh.qty, 0), 0)
                        ELSE 0 END AS short_by,
                   CASE
                     -- HIS OWN RULE: blank means do not track this part, and
                     -- it must never read as nought.
                     WHEN COALESCE(l.min_qty, 0) <= 0
                          AND f.state = 'unmatched' THEN 'unmatched'
                     WHEN COALESCE(l.min_qty, 0) <= 0 THEN 'untracked'
                     -- "when stock gets to this number or lower" - his words
                     -- in the spreadsheet, so at the minimum IS below it.
                     WHEN COALESCE(oh.qty, 0) <= l.min_qty THEN 'below'
                     ELSE 'ok'
                   END AS status,
                   CASE
                     WHEN COALESCE(l.min_qty, 0) > 0 THEN NULL
                     WHEN f.code IS NULL THEN
                       'No figure was given for this part in the file'
                     WHEN f.state = 'unmatched' THEN f.note
                     ELSE 'A minimum was loaded for this part and has gone since'
                   END AS why
              FROM product_product pp
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
              JOIN uom_uom uom ON uom.id = pt.uom_id
              LEFT JOIN on_hand oh ON oh.product_id = pp.id
              LEFT JOIN levels l ON l.product_id = pp.id
              LEFT JOIN vend v ON v.product_tmpl_id = pt.id
              LEFT JOIN from_file f ON f.code = pp.default_code
             WHERE pp.active AND pt.active AND pt.is_storable
            )
        """ % self._table)

    # --- getting at the numbers from the screen -------------------------------

    def action_edit_levels(self):
        """Open this part's reordering rule, making one if it has none.

        A REPORT CANNOT BE TYPED INTO - it is a database view - and he will
        want to change a minimum the moment he disagrees with one. Rather than
        send him to find Replenishment, the row opens its own rule.
        """
        self.ensure_one()
        orderpoint = self.env["stock.warehouse.orderpoint"].search(
            [("product_id", "=", self.product_id.id)], limit=1)

        if not orderpoint:
            warehouse = self.env["stock.warehouse"].search(
                [("company_id", "=", self.env.company.id)], limit=1)
            # BY A REAL USER, like every rule this module writes. A manual
            # rule owned by the superuser is one Odoo's autovacuum deletes the
            # moment the part is well stocked - see `levels_user`.
            from .minmax_load import levels_user

            orderpoint = self.env["stock.warehouse.orderpoint"].sudo().with_user(
                levels_user(self.env)).create({
                "product_id": self.product_id.id,
                "warehouse_id": warehouse.id,
                "location_id": warehouse.lot_stock_id.id,
                # MANUAL, like every rule this module writes - see the loader.
                "trigger": "manual",
                "product_min_qty": 0.0,
                "product_max_qty": 0.0,
            })

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.warehouse.orderpoint",
            "res_id": orderpoint.id,
            "view_mode": "form",
            "target": "new",
            "name": self.product_id.display_name,
        }

    @api.model
    def action_load_levels(self):
        """Re-read the shipped file. Reports what it did, and what it would not."""
        from .minmax_load import load_levels

        return load_levels(self.env)
