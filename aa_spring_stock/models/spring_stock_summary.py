from odoo import fields, models, tools


class AaSpringStockSummary(models.Model):
    """One row per wire and I.D.: LH and RH side by side, Floor / Rack / Boxes.

    Read straight from the coil quants (COIL-<wire>-<I.D.>-<L/R>), so it is
    always current. Alerts as in the owner's spreadsheet: one usable pair or
    less on the floor means open a box; and with no box behind it either, order
    from the supplier.
    """

    _name = "aa.spring.stock.summary"
    _description = "Spring Inventory Summary"
    _auto = False
    _order = "inside_diameter_num, wire"

    wire = fields.Char(string="Wire", readonly=True)
    inside_diameter = fields.Char(string="I.D.", readonly=True)
    inside_diameter_num = fields.Float(readonly=True)
    floor_l_in = fields.Float(string="Floor LH (in)", readonly=True, digits=(16, 1))
    floor_r_in = fields.Float(string="Floor RH (in)", readonly=True, digits=(16, 1))
    floor_l_pcs = fields.Integer(string="Floor LH Coils", readonly=True)
    floor_r_pcs = fields.Integer(string="Floor RH Coils", readonly=True)
    floor_pairs = fields.Integer(string="Floor Pairs", readonly=True)
    rack_l_in = fields.Float(string="Rack LH (in)", readonly=True, digits=(16, 1))
    rack_r_in = fields.Float(string="Rack RH (in)", readonly=True, digits=(16, 1))
    rack_l_pcs = fields.Integer(string="Rack LH Pieces", readonly=True)
    rack_r_pcs = fields.Integer(string="Rack RH Pieces", readonly=True)
    boxes_l_pcs = fields.Integer(string="Boxes LH Coils", readonly=True)
    boxes_r_pcs = fields.Integer(string="Boxes RH Coils", readonly=True)
    total_l_in = fields.Float(string="Total LH (in)", readonly=True, digits=(16, 1))
    total_r_in = fields.Float(string="Total RH (in)", readonly=True, digits=(16, 1))
    alert = fields.Selection([
        ("ok", "OK"),
        ("open_box", "Low - Open a Box"),
        ("order", "No Backup - Order from Supplier"),
    ], string="Alert", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
            WITH pieces AS (
                SELECT split_part(pp.default_code, '-', 2) AS wire,
                       split_part(pp.default_code, '-', 3) AS id_code,
                       split_part(pp.default_code, '-', 4) AS hand,
                       sl.name AS place,
                       q.quantity AS qty
                  FROM stock_quant q
                  JOIN product_product pp ON pp.id = q.product_id
                  JOIN stock_location sl ON sl.id = q.location_id
                 WHERE pp.default_code LIKE 'COIL-%%'
                   AND sl.usage = 'internal'
                   AND q.quantity > 0.001
            ), coils AS (
                SELECT DISTINCT split_part(default_code, '-', 2) AS wire,
                       split_part(default_code, '-', 3) AS id_code
                  FROM product_product
                 WHERE default_code LIKE 'COIL-%%' AND active
            ), sums AS (
                SELECT c.wire, c.id_code,
                  COALESCE(SUM(p.qty) FILTER (WHERE p.place = 'Floor' AND p.hand = 'L'), 0) AS floor_l_in,
                  COALESCE(SUM(p.qty) FILTER (WHERE p.place = 'Floor' AND p.hand = 'R'), 0) AS floor_r_in,
                  COUNT(p.qty) FILTER (WHERE p.place = 'Floor' AND p.hand = 'L') AS floor_l_pcs,
                  COUNT(p.qty) FILTER (WHERE p.place = 'Floor' AND p.hand = 'R') AS floor_r_pcs,
                  COALESCE(SUM(p.qty) FILTER (WHERE p.place = 'Rack' AND p.hand = 'L'), 0) AS rack_l_in,
                  COALESCE(SUM(p.qty) FILTER (WHERE p.place = 'Rack' AND p.hand = 'R'), 0) AS rack_r_in,
                  COUNT(p.qty) FILTER (WHERE p.place = 'Rack' AND p.hand = 'L') AS rack_l_pcs,
                  COUNT(p.qty) FILTER (WHERE p.place = 'Rack' AND p.hand = 'R') AS rack_r_pcs,
                  COUNT(p.qty) FILTER (WHERE p.place = 'Boxes' AND p.hand = 'L') AS boxes_l_pcs,
                  COUNT(p.qty) FILTER (WHERE p.place = 'Boxes' AND p.hand = 'R') AS boxes_r_pcs,
                  COALESCE(SUM(p.qty) FILTER (WHERE p.hand = 'L'), 0) AS total_l_in,
                  COALESCE(SUM(p.qty) FILTER (WHERE p.hand = 'R'), 0) AS total_r_in
                FROM coils c
                LEFT JOIN pieces p ON p.wire = c.wire AND p.id_code = c.id_code
                GROUP BY c.wire, c.id_code
            )
            SELECT row_number() OVER (ORDER BY id_code, wire) AS id,
                   wire,
                   CASE id_code WHEN '2.625' THEN '2 5/8"' WHEN '3.75' THEN '3 3/4"'
                                WHEN '5.25' THEN '5 1/4"' ELSE id_code END AS inside_diameter,
                   CASE WHEN id_code ~ '^[0-9.]+$' THEN id_code::numeric ELSE 0 END AS inside_diameter_num,
                   floor_l_in, floor_r_in, floor_l_pcs, floor_r_pcs,
                   LEAST(floor_l_pcs, floor_r_pcs) AS floor_pairs,
                   rack_l_in, rack_r_in, rack_l_pcs, rack_r_pcs,
                   boxes_l_pcs, boxes_r_pcs, total_l_in, total_r_in,
                   CASE
                     WHEN LEAST(floor_l_pcs, floor_r_pcs) <= 1
                          AND (boxes_l_pcs = 0 OR boxes_r_pcs = 0) THEN 'order'
                     WHEN LEAST(floor_l_pcs, floor_r_pcs) <= 1 THEN 'open_box'
                     ELSE 'ok'
                   END AS alert
              FROM sums
            )
        """ % self._table)
