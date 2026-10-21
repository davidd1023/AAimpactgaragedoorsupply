from odoo import fields, models, tools


class AaSpringPlaceSummary(models.Model):
    """The spring inventory of one place: Floor, Rack or Boxes.

    One row per wire and I.D. (and per box, for the Boxes), LH and RH side by
    side. Read straight from the coil quants, so it is always current.
    """

    _name = "aa.spring.place.summary"
    _description = "Spring Inventory by Place"
    _auto = False
    _order = "place, box_number, inside_diameter_num, wire"

    place = fields.Selection([("Floor", "Floor"), ("Rack", "Rack"), ("Boxes", "Boxes")],
                             string="Place", readonly=True)
    box_id = fields.Many2one("aa.spring.box", string="Box", readonly=True)
    box_number = fields.Integer(string="Box #", readonly=True)
    wire = fields.Char(string="Wire", readonly=True)
    inside_diameter = fields.Char(string="I.D.", readonly=True)
    inside_diameter_num = fields.Float(readonly=True)
    l_pcs = fields.Integer(string="LH Pieces", readonly=True)
    r_pcs = fields.Integer(string="RH Pieces", readonly=True)
    pairs = fields.Integer(string="Pairs", readonly=True)
    l_in = fields.Float(string="LH (in)", readonly=True, digits=(16, 1))
    r_in = fields.Float(string="RH (in)", readonly=True, digits=(16, 1))
    l_longest = fields.Float(string="Longest LH (in)", readonly=True, digits=(16, 2))
    r_longest = fields.Float(string="Longest RH (in)", readonly=True, digits=(16, 2))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
            WITH pieces AS (
                SELECT split_part(pp.default_code, '-', 2) AS wire,
                       split_part(pp.default_code, '-', 3) AS id_code,
                       split_part(pp.default_code, '-', 4) AS hand,
                       CASE WHEN sl.name IN ('Floor', 'Rack', 'Boxes') THEN sl.name
                            ELSE parent.name END AS place,
                       box.id AS box_id,
                       box.number AS box_number,
                       q.quantity AS qty
                  FROM stock_quant q
                  JOIN product_product pp ON pp.id = q.product_id
                  JOIN stock_location sl ON sl.id = q.location_id
                  LEFT JOIN stock_location parent ON parent.id = sl.location_id
                  LEFT JOIN aa_spring_box box ON box.location_id = sl.id
                 WHERE pp.default_code LIKE 'COIL-%%'
                   AND sl.usage = 'internal'
                   AND q.quantity > 0.001
            ), sums AS (
                SELECT place, box_id, box_number, wire, id_code,
                  COUNT(qty) FILTER (WHERE hand = 'L') AS l_pcs,
                  COUNT(qty) FILTER (WHERE hand = 'R') AS r_pcs,
                  COALESCE(SUM(qty) FILTER (WHERE hand = 'L'), 0) AS l_in,
                  COALESCE(SUM(qty) FILTER (WHERE hand = 'R'), 0) AS r_in,
                  COALESCE(MAX(qty) FILTER (WHERE hand = 'L'), 0) AS l_longest,
                  COALESCE(MAX(qty) FILTER (WHERE hand = 'R'), 0) AS r_longest
                FROM pieces
                WHERE place IN ('Floor', 'Rack', 'Boxes')
                GROUP BY place, box_id, box_number, wire, id_code
            )
            SELECT row_number() OVER (ORDER BY place, box_number, id_code, wire) AS id,
                   place, box_id, COALESCE(box_number, 0) AS box_number, wire,
                   CASE id_code WHEN '2.625' THEN '2 5/8"' WHEN '3.75' THEN '3 3/4"'
                                WHEN '5.25' THEN '5 1/4"' ELSE id_code END AS inside_diameter,
                   CASE WHEN id_code ~ '^[0-9.]+$' THEN id_code::numeric ELSE 0 END AS inside_diameter_num,
                   l_pcs, r_pcs, LEAST(l_pcs, r_pcs) AS pairs,
                   l_in, r_in, l_longest, r_longest
              FROM sums
            )
        """ % self._table)
