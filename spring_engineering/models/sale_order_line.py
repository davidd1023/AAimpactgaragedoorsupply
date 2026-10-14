from odoo import api, fields, models


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
            # EVERY JAMB BRACKET TAKES ONE OF EACH. Not per track and not per
            # door: per bracket, wherever the bracket came from, which is why
            # these two carry no parent - they answer to the whole cart.
            ("stud", "Knurled studs"),
            ("nut", "Flange nuts"),
        ],
        string="Preparation part",
        copy=False,
    )

    # --- what the customer SPECIFIED, as data rather than as prose -----------
    #
    # ODOO REWRITES THE DESCRIPTION, AND THAT IS WHAT WENT WRONG. `name` is a
    # stored COMPUTED field: core recomputes it from the product whenever
    # product_id, linked_line_id or linked_line_ids changes. A kit ordered with
    # extras changes both of the last two - the extras are created pointing at
    # the kit line - so every recompute threw away whatever had been written
    # there:
    #
    #   * the spring's full specification, written by add_assembly_lines and
    #     then wiped the moment the line was linked to its kit, leaving
    #     "Custom Torsion Spring Assembly / Wound to the specification on the
    #     order line." - no wire, no length, no door. That is why a kit's
    #     spring printed under Hardware with no detail while the calculator's
    #     printed perfectly: the calculator's spring is linked to nothing.
    #
    #   * the dealer kit's door note, for the same reason.
    #
    # So the specification is STORED, and the description is rebuilt from it
    # every time Odoo recomputes. It cannot be lost again, because it is no
    # longer kept in the thing being recomputed.
    aa_spec_note = fields.Text(
        string="Specification",
        copy=True,
        help="Kept out of the description so a recompute cannot lose it; "
             "appended to the description every time one happens.",
    )

    # THE DOOR AS NUMBERS. The work order sheet used to read these back out of
    # the description, which worked until something else in the text looked
    # like a door: the Drum option is labelled with its rating - "D400-96 (up
    # to 530 lb)" - and the first weight in the text won, so a 355 lb door
    # printed as 530 lb. A figure that was entered as a number is stored as a
    # number.
    aa_door_width_in = fields.Float(string="Door width (in)", copy=True)
    aa_door_height_in = fields.Float(string="Door height (in)", copy=True)
    aa_door_weight_lb = fields.Float(string="Door weight (lb)", copy=True)
    aa_door_hi_lift_in = fields.Float(string="Hi-lift (in)", copy=True)
    aa_door_cycles = fields.Char(string="Cycle target", copy=True)

    # THE DEPENDS ARE REPEATED, which is belt and braces rather than strictly
    # needed: Odoo 19 MERGES the @api.depends of every override of a compute
    # method, so core's product_id, linked_line_id and linked_line_ids survive
    # whatever is declared here. They are written out anyway because an
    # override that quietly narrowed them would be a hard bug to see, and a
    # test asserts the merged list still carries all four names.
    #
    # aa_spec_note is the one this adds, so writing a specification refreshes
    # the description by itself rather than needing the caller to remember.
    @api.depends("product_id", "linked_line_id", "linked_line_ids", "aa_spec_note")
    def _compute_name(self):
        super()._compute_name()

        for line in self:
            note = (line.aa_spec_note or "").strip()

            if not note:
                continue

            name = (line.name or "").strip()

            # Core skips lines with no product, so the note could otherwise be
            # appended to a description that already ends with it.
            if note in name:
                continue

            line.name = f"{name}\n{note}" if name else note

    def aa_write_door(self, door, note=""):
        """Record the door this line is for, and the note that describes it.

        `door` is in INCHES and POUNDS, as the pages that collect it work.
        Written in one go so the description is recomputed once.
        """
        values = {
            "aa_door_width_in": float(door.get("width_in") or 0),
            "aa_door_height_in": float(door.get("height_in") or 0),
            "aa_door_weight_lb": float(door.get("weight_lb") or 0),
            "aa_door_hi_lift_in": float(door.get("hi_lift_in") or 0),
            "aa_door_cycles": door.get("cycles") or "",
        }

        if note:
            values["aa_spec_note"] = note

        self.write(values)
