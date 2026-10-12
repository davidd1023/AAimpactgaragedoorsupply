from odoo import fields, models


class DoorWorkOrderMark(models.Model):
    """One door design on the order - mark A, mark B - and how many of it.

    WHY A MARK IS ITS OWN RECORD. An order carries several marks, each a
    different door, and every number on the info papers belongs to one of them:
    a 7 ft mark and a 9 ft mark have different track lengths, different cable
    lengths, different drums. Holding those on the manufacturing order itself
    would only work while an order had exactly one door in it, which was never
    true - the calculator has had marks and quantities all along, and nothing
    downstream read them.
    """

    _name = "door.work.order.mark"
    _description = "Garage Door Work Order Mark"
    _order = "production_id, sequence, id"

    production_id = fields.Many2one(
        "mrp.production", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    label = fields.Char(string="Mark", required=True)
    door_qty = fields.Integer(
        string="Doors", required=True, default=1,
        help="How many doors of this mark the order is for.")

    item_ids = fields.One2many(
        "door.work.order.item", "mark_id", string="Cut List")

    # The door, as the calculator described it.
    width = fields.Float(string="Width (in)")
    height = fields.Float(string="Height (in)")
    weight = fields.Float(string="Weight (lb)")
    track_label = fields.Char(string="Track")
    config = fields.Char(string="Configuration")
    projection = fields.Float(string="2x2 Projection (in)")
    sections = fields.Integer()

    # The cable side, which only exists when a door weight was given.
    drum = fields.Char()
    ebf = fields.Char(string="EBF")
    capacity = fields.Float(string="Capacity Per Drum (lb)")
    ftsc = fields.Float(string="FTSC (in)")
    cable_type = fields.Char()

    # Zero means "not called for", which is what the calculator prints as "--".
    jb_10 = fields.Integer(string="J-10")
    jb_12 = fields.Integer(string="J-12")
    jb_14 = fields.Integer(string="J-14")
    jb_16 = fields.Integer(string="J-16")

    def _door_wo_item_length(self, role):
        """The cut length for one role on this mark, for the papers."""
        self.ensure_one()

        return self.item_ids.filtered(lambda i: i.role == role)[:1].length_label or ""
