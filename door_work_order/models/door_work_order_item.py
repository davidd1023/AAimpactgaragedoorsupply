from odoo import fields, models


class DoorWorkOrderItem(models.Model):
    """One cut on the shop floor: a length, a quantity and what to cut it from.

    A STRUCTURED LIST RATHER THAN A NOTE. The whole point of sending this to
    manufacturing is that somebody has to cut a track to 76 1/4" and a pair of
    cables to 123", and a free-text note cannot be sorted, totalled, printed per
    station or checked off. It also cannot be wrong in a way anyone notices,
    which is the real argument: a field that holds 76.25 can be compared against
    what was actually cut, and a sentence cannot.
    """

    _name = "door.work.order.item"
    _description = "Garage Door Work Order Cut Item"
    _order = "production_id, sequence, id"

    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    role = fields.Selection(
        [
            ("track_vertical", "Vertical Track"),
            ("track_horizontal", "Horizontal Track"),
            ("cable", "Cable"),
        ],
        required=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Cut From",
        help="The stock item this length is cut from.",
    )
    length_inches = fields.Float(
        string="Length (in)",
        required=True,
        digits=(16, 4),
        help="The finished length of ONE piece, in inches.",
    )
    quantity = fields.Integer(
        string="Pieces",
        required=True,
        default=2,
        help="How many pieces of this length. Tracks and cables come in pairs,"
             " so this is normally 2 - one for each side of the door.",
    )
    # Kept as text rather than computed from length_inches so that what the
    # calculator SAID is preserved exactly as the shop floor read it. 76.25
    # formats to 76 1/4", but a value arriving as 76.26 should not be quietly
    # displayed as 76 1/4" - the discrepancy is the interesting part.
    length_label = fields.Char(
        string="As Calculated",
        help="The length exactly as the calculator printed it.",
    )
    note = fields.Char()
