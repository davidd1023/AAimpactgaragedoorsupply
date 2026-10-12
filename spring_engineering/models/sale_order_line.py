from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # WHICH TRACK LINE A PREPARATION PART BELONGS TO.
    #
    # Without this link the jamb brackets and flag angle are loose lines: change
    # the track quantity from 1 to 2 and the customer is shipped one door's
    # worth of brackets for two doors' worth of track, and nothing in the order
    # says they were ever related. The link lets the quantities follow the
    # track, and `ondelete="cascade"` means removing the track removes its parts
    # instead of leaving them orphaned in the cart.
    # WHAT THE CALCULATOR WORKED OUT, KEPT AS DATA.
    #
    # Until now the only record of a configured assembly was the line's
    # description - a block of English assembled for the customer to read. The
    # shop floor needs the same figures to build from, and parsing them back
    # out of a sentence is how a wire size ends up off by a decimal place. They
    # are written here at the moment they are validated, from the same numbers
    # the price was computed from, so the sheet and the price cannot disagree.
    #
    # An assembly is one spring or a nested pair - the controller refuses
    # anything else - so two slots is the whole range, not a simplification.
    spring_assembly = fields.Char(string="Assembly", copy=False)
    spring_count = fields.Integer(string="Springs", copy=False)
    spring_door_weight = fields.Float(string="Door Weight (lb)", copy=False)
    spring_door_height = fields.Char(string="Door Height", copy=False)
    spring_cycles = fields.Integer(string="Cycle Target", copy=False)
    spring_steel_weight = fields.Float(
        string="Steel Per Assembly (lb)", copy=False,
        help="Wire weight of one assembly, which is what the steel was priced on.")
    spring_filler_feet = fields.Float(string="Filler (ft)", copy=False)

    spring_a_role = fields.Char(copy=False)
    spring_a_wire = fields.Float(string="Wire A", digits=(16, 4), copy=False)
    spring_a_id = fields.Float(string="ID A", digits=(16, 4), copy=False)
    spring_a_length = fields.Float(string="Length A", digits=(16, 2), copy=False)

    spring_b_role = fields.Char(copy=False)
    spring_b_wire = fields.Float(string="Wire B", digits=(16, 4), copy=False)
    spring_b_id = fields.Float(string="ID B", digits=(16, 4), copy=False)
    spring_b_length = fields.Float(string="Length B", digits=(16, 2), copy=False)

    def spring_parameter_rows(self):
        """The assembly as a list of (label, value), for printing.

        Built here rather than in the report because these are this module's
        numbers and their units belong with them - a bare 0.2625 on a shop
        sheet is a trap.
        """
        self.ensure_one()

        if not self.spring_assembly:
            return []

        rows = [
            ("Assembly", self.spring_assembly),
            ("Springs", "%d" % self.spring_count),
            ("Door weight", "%g lb" % self.spring_door_weight),
            ("Door height", self.spring_door_height or ""),
            ("Cycle target", "{:,}".format(self.spring_cycles)),
        ]

        if self.spring_steel_weight:
            rows.append(("Steel per assembly", "%.2f lb" % self.spring_steel_weight))

        if self.spring_filler_feet:
            rows.append(("Plastic filler", "%g ft" % self.spring_filler_feet))

        return rows

    def spring_detail_rows(self):
        """One row per spring: role, wire, inside diameter, length."""
        self.ensure_one()
        out = []

        for role, wire, diameter, length in (
            (self.spring_a_role, self.spring_a_wire, self.spring_a_id,
             self.spring_a_length),
            (self.spring_b_role, self.spring_b_wire, self.spring_b_id,
             self.spring_b_length),
        ):
            if not role:
                continue

            out.append({
                "role": role,
                "wire": '%g"' % wire,
                "inside_diameter": '%g"' % diameter,
                "length": '%g"' % length,
            })

        return out

    track_prep_parent_id = fields.Many2one(
        "sale.order.line",
        string="Prepared track this part is for",
        ondelete="cascade",
        index=True,
        copy=False,
    )

    # What the part is for, so the sync knows how to recompute its quantity -
    # brackets scale with the door height, the flag angle is one per track.
    # ONE ROLE PER BRACKET SIZE, because a prepared pair ships a graduated mix
    # - four #10, five #12, five #14 and sometimes #16 - and each size is its
    # own product on its own line. A single "jamb" role could not tell two
    # bracket lines apart, so the sync would keep overwriting one with the
    # other's quantity.
    track_prep_role = fields.Selection(
        [
            ("jamb_10", "Jamb brackets #10"),
            ("jamb_12", "Jamb brackets #12"),
            ("jamb_14", "Jamb brackets #14"),
            ("jamb_16", "Jamb brackets #16"),
            ("flag", "Flag angle"),
        ],
        string="Preparation part",
        copy=False,
    )
