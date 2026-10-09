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
    track_prep_parent_id = fields.Many2one(
        "sale.order.line",
        string="Prepared track this part is for",
        ondelete="cascade",
        index=True,
        copy=False,
    )

    # What the part is for, so the sync knows how to recompute its quantity -
    # brackets scale with the door height, the flag angle is one per track.
    track_prep_role = fields.Selection(
        [("jamb", "Jamb brackets"), ("flag", "Flag angle")],
        string="Preparation part",
        copy=False,
    )
