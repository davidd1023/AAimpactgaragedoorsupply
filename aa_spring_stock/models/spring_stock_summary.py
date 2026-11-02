from odoo import fields, models, tools


class AaSpringStockSummary(models.Model):
    """One row per wire and I.D.: LH and RH side by side, Floor / Rack / Boxes.

    Read straight from the coil quants (COIL-<wire>-<I.D.>-<L/R>), so it is
    always current. Alerts as in the owner's spreadsheet: one usable pair or
    less on the floor means open a box; and with no box behind it either, order
    from the supplier.

    AND HOW LONG IT WILL LAST (owner, 2026-10-28): *"I want it to track the
    spring wire size and id inventory and send a warning somewhere that at the
    current pace of orders being made we will likely run out of material in x
    amount of days."*

    Nothing had to be measured for this - both halves were already being
    recorded. `aa.spring.cut` has logged every spring ever cut, dated, with
    its wire, its I.D. and its length in inches; the quants hold what is left.
    Inches on hand divided by inches a day is the answer, and the only real
    work was deciding what each of those two numbers means.

    **THE WORSE HAND DECIDES.** A spring takes a LH piece and a RH piece, so a
    size with a mountain of LH and no RH has run out - exactly the reasoning
    behind the pairs alert above. `days_left` is therefore the SMALLER of the
    two hands' own figures, and Postgres `LEAST` ignores nulls, which is what
    makes a hand with no demand at all drop out of the comparison instead of
    dragging it to zero.

    **FREE INCHES, NOT INCHES.** What is on the floor is not all available: a
    confirmed order has already reserved the piece each spring is cut from. So
    the sum is `quantity - reserved_quantity` - the inches nothing has claimed
    yet. Counting reserved inches would promise material that is spoken for.

    **NO PACE MEANS NO ANSWER.** A size nobody has cut in the window gets a
    blank, not a warning and not "forever". He asked what happens at the
    CURRENT pace; where there is no pace there is nothing to say, and a
    warning on a size that never moves is noise that would cost the real ones
    their credibility.

    **A CUT NOBODY COULD MAKE IS STILL DEMAND.** The pace counts `done` and
    `short` cuts - `short` being an order that wanted that size and found no
    piece long enough. Leaving those out would understate the pace at exactly
    the moment stock is tightest, which is the worst time to be optimistic.
    They cannot double-count: a replan unlinks a cut that is not done before
    writing the new one.

    Both numbers behind it are SETTINGS (Inventory > Configuration >
    Settings), read live by the view: how far back to measure the pace, and
    how few days left is worth a warning. A value somebody has mistyped falls
    back to the default rather than taking the screen down with it.
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

    # --- how long it will last ------------------------------------------------
    free_l_in = fields.Float(string="Free LH (in)", readonly=True, digits=(16, 1),
                             help="Inches on hand that no confirmed order has reserved.")
    free_r_in = fields.Float(string="Free RH (in)", readonly=True, digits=(16, 1),
                             help="Inches on hand that no confirmed order has reserved.")
    used_per_day_in = fields.Float(
        string="Used / Day (in)", readonly=True, digits=(16, 1),
        help="Inches of this size cut per day, measured over the period set in "
             "Inventory > Configuration > Settings. Both hands together, so it "
             "is roughly twice what one spring takes.")
    cuts_counted = fields.Integer(
        string="Cuts Counted", readonly=True,
        help="How many springs that rate was worked out from. A rate from one "
             "or two cuts is a guess; the more cuts behind it, the more it "
             "means.")
    days_left = fields.Float(
        string="Days Left", readonly=True, digits=(16, 0),
        help="At the pace of recent orders, how long the free inches last - "
             "whichever hand runs out first. Blank when this size has not "
             "been cut at all in the period, because then there is no pace to "
             "work from.")
    runout = fields.Selection([
        ("none", "No recent orders"),
        ("ok", "OK"),
        ("soon", "Running Out"),
        ("now", "Out of Material"),
    ], string="Run-out", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
            WITH settings AS (
                -- READ LIVE, so changing the setting changes the screen with
                -- no recompute and no module update. A value somebody typed
                -- badly falls back to the default: a mistyped number is not
                -- worth taking the inventory screen down for.
                SELECT
                  COALESCE((SELECT CASE WHEN value ~ '^[0-9]+$' AND value::numeric > 0
                                        THEN value::numeric END
                              FROM ir_config_parameter
                             WHERE key = 'aa_spring_stock.pace_days'), 30) AS pace_days,
                  COALESCE((SELECT CASE WHEN value ~ '^[0-9]+$'
                                        THEN value::numeric END
                              FROM ir_config_parameter
                             WHERE key = 'aa_spring_stock.runout_warn_days'), 14) AS warn_days
            ), usage AS (
                -- WHAT HAS BEEN CUT, per wire, I.D. and hand.
                --
                -- JOINED BY PRODUCT, NEVER BY THE LABELS. `aa.spring.cut`
                -- stores `inside_diameter` as the PRETTY label ('2 5/8"')
                -- while everything here groups by the code ('2.625'), so
                -- matching on those two Char columns would silently line up
                -- nothing at all. The coil product's own `default_code` is
                -- the one spelling both sides already agree on.
                SELECT split_part(pp.default_code, '-', 2) AS wire,
                       split_part(pp.default_code, '-', 3) AS id_code,
                       split_part(pp.default_code, '-', 4) AS hand,
                       SUM(c.length) AS inches,
                       COUNT(*) AS cuts
                  FROM aa_spring_cut c
                  JOIN product_product pp ON pp.id = c.product_id
                  CROSS JOIN settings s
                 WHERE c.state IN ('done', 'short')
                   AND c.length > 0
                   -- UTC EXPLICITLY. `aa_spring_cut.date` is a naive
                   -- timestamp holding UTC, Odoo's convention; bare
                   -- `now()` is a timestamptz and Postgres would cast
                   -- it using the SESSION's timezone, sliding the
                   -- window by however many hours that happens to be.
                   AND c.date >= (now() AT TIME ZONE 'UTC')
                                 - (s.pace_days || ' days')::interval
                 GROUP BY 1, 2, 3
            ), pieces AS (
                SELECT split_part(pp.default_code, '-', 2) AS wire,
                       split_part(pp.default_code, '-', 3) AS id_code,
                       split_part(pp.default_code, '-', 4) AS hand,
                       CASE WHEN sl.name IN ('Floor', 'Rack', 'Boxes') THEN sl.name
                            ELSE parent.name END AS place,
                       q.quantity AS qty,
                       GREATEST(q.quantity - q.reserved_quantity, 0) AS free
                  FROM stock_quant q
                  JOIN product_product pp ON pp.id = q.product_id
                  JOIN stock_location sl ON sl.id = q.location_id
                  LEFT JOIN stock_location parent ON parent.id = sl.location_id
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
                  COALESCE(SUM(p.qty) FILTER (WHERE p.hand = 'R'), 0) AS total_r_in,
                  -- FREE inches: what no confirmed order has reserved. The
                  -- reservation IS the planned cut, so this needs no join to
                  -- the cut log at all.
                  COALESCE(SUM(p.free) FILTER (WHERE p.hand = 'L'), 0) AS free_l_in,
                  COALESCE(SUM(p.free) FILTER (WHERE p.hand = 'R'), 0) AS free_r_in
                FROM coils c
                LEFT JOIN pieces p ON p.wire = c.wire AND p.id_code = c.id_code
                GROUP BY c.wire, c.id_code
            ), paced AS (
                SELECT s.*,
                       COALESCE(ul.inches, 0) / st.pace_days AS l_per_day,
                       COALESCE(ur.inches, 0) / st.pace_days AS r_per_day,
                       COALESCE(ul.cuts, 0) + COALESCE(ur.cuts, 0) AS cuts_counted,
                       st.warn_days
                  FROM sums s
                  CROSS JOIN settings st
                  LEFT JOIN usage ul
                         ON ul.wire = s.wire AND ul.id_code = s.id_code AND ul.hand = 'L'
                  LEFT JOIN usage ur
                         ON ur.wire = s.wire AND ur.id_code = s.id_code AND ur.hand = 'R'
            ), covered AS (
                SELECT p.*,
                       -- NULL WHERE THERE IS NO PACE, which is what makes
                       -- LEAST below ignore that hand rather than read it as
                       -- nothing left. A hand nobody has ordered cannot run
                       -- out.
                       CASE WHEN p.l_per_day > 0 THEN p.free_l_in / p.l_per_day END AS l_days,
                       CASE WHEN p.r_per_day > 0 THEN p.free_r_in / p.r_per_day END AS r_days
                  FROM paced p
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
                   END AS alert,
                   free_l_in, free_r_in,
                   l_per_day + r_per_day AS used_per_day_in,
                   cuts_counted,
                   -- THE WORSE HAND DECIDES. Postgres LEAST returns the
                   -- smallest NON-NULL, so a hand with no demand drops out
                   -- of the comparison and only a size nobody has cut in
                   -- either hand comes back blank.
                   LEAST(l_days, r_days) AS days_left,
                   CASE
                     WHEN LEAST(l_days, r_days) IS NULL THEN 'none'
                     WHEN LEAST(l_days, r_days) < 1 THEN 'now'
                     WHEN LEAST(l_days, r_days) <= warn_days THEN 'soon'
                     ELSE 'ok'
                   END AS runout
              FROM covered
            )
        """ % self._table)
