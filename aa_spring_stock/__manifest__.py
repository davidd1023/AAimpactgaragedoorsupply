{
    'name': 'AA Spring Stock',
    'version': '19.0.1.2.0',
    'summary': 'Spring orders consume coil inches; a plain view of the spring inventory',
    'description': """
Spring coils (COIL-<wire>-<I.D.>-<L/R>, kept in inches, one lot per piece) are
consumed by the Springs manufacturing order of each custom spring.

* When the order is confirmed, each spring is assigned the piece it is cut from
  and that piece is reserved, so two orders never count on the same inches.
  Order of preference (owner, 2026-10-19): a leftover piece on the Rack that is
  long enough (the shortest one that fits), then a coil on the Floor (the
  shortest one that fits, so opened coils are used up first), and only then a
  coil from the Boxes.
* A piece left shorter than 16" after a cut is scrapped.
* The Springs card shows which piece to cut each spring from.
* When the order is done the inches are taken off that piece. A coil taken from
  a Box is moved to the Floor, since it has been opened.
* Inventory > Springs: a summary per wire and I.D. (L and R side by side, with
  reorder alerts), the leftover pieces on the Rack, and the cut history.
* Floor / Rack / Boxes: one page, a fold-out group per place, per wire and I.D.
* Spring Boxes: numbered boxes (Box 1, Box 2...), each its own location under
  Boxes. Add coils to a box (wire, I.D., LH / RH count - one box can hold
  several sizes), move some of them to the floor, and remove the box once it is
  empty (owner, 2026-10-19).
""",
    'author': 'AA Impact Garage Door Supply',
    'category': 'Inventory/Inventory',
    'depends': ['stock', 'mrp', 'aa_shop_floor', 'work_order_sheet'],
    'data': [
        'security/ir.model.access.csv',
        'views/spring_stock_views.xml',
        'views/spring_box_views.xml',
        'data/spring_box_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
