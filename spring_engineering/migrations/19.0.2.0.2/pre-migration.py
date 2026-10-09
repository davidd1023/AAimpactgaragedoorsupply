"""Take the Trims attribute back off the hardware kits.

WHY THIS EXISTS. The trim colour was added as a product attribute and attached
automatically to every product named "hardware kit". The owner reports that
since it went on, the kits stopped adding the other products they used to add
to an order - the kit line arrives alone. That could not be reproduced here:
on a dev kit built to the same shape, adding it leaves other cart lines
untouched and the sync removes nothing it should not. But it is a live shop,
the damage is real, and the owner asked for a revert rather than another round
of hypotheses. The right call is to put the kits back and find another way to
do trims.

REMOVING THE CODE IS NOT ENOUGH. The attribute was attached to the products by
a function that ran on every module update, so the attribute LINES are sitting
in the database. Dropping the data file would orphan them - Odoo would try to
delete the records at the end of the update and fail on the order lines that
reference them, which is exactly how the garage_door_supply move went wrong.
So they are removed here, deliberately and in the right order.

IT WILL NOT TOUCH A CONFIRMED ORDER. A quote or order that recorded a trim
colour is history, and silently rewriting it would be worse than leaving the
attribute in place. Draft website carts are fair game - they are shopping
sessions, not records - so their references are cleared first. If anything
other than a draft refers to a trim value, the whole removal is skipped and a
warning is logged, leaving a database that still works.
"""

import logging

_logger = logging.getLogger(__name__)

NAMES = (
    "attribute_trim_colour",
    "attribute_value_trim_none",
    "attribute_value_trim_black",
    "attribute_value_trim_bronze",
    "attribute_value_trim_white",
)
MODULE = "spring_engineering"


def _res_id(cr, name):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s",
        (MODULE, name),
    )
    row = cr.fetchone()

    return row[0] if row else None


def _orphan_trim_attributes(cr):
    """Trim attributes this feature left behind with no external ID.

    The module move produced these: a migration deleted an ir_model_data row
    while the record it pointed at survived, so the attribute is still on
    products but nothing owns it. A revert that only follows external IDs
    leaves the option on the page.

    Matched on the VALUE NAMES, not on the attribute's name. "Trims" is a word
    the owner may well use for something of their own; "Black, 3 Trim" beside
    "No Trims" is this feature's fingerprint and nobody else's.

    AND ONLY ON THOSE FOUR EXACT STRINGS. The first version of this also
    matched the bare words Black, Bronze and White, which is not a fingerprint
    of anything - it is what a colour attribute looks like. Any three-colour
    attribute of the owner's with no external ID would have matched and been
    DELETED, on a live shop, by a migration meant to clean up after me. That
    was a genuinely dangerous rule and it is gone. "Black, 3 Trim" is a string
    no one types by accident.
    """
    cr.execute(
        """
        SELECT pa.id
          FROM product_attribute pa
         WHERE NOT EXISTS (
                   SELECT 1 FROM ir_model_data d
                    WHERE d.model = 'product.attribute' AND d.res_id = pa.id
               )
           AND (
                   SELECT COUNT(*)
                     FROM product_attribute_value v
                    WHERE v.attribute_id = pa.id
                      AND v.name->>'en_US' IN (
                          'No Trims', 'Black, 3 Trim', 'Bronze, 3 Trim',
                          'White, 3 Trim'
                      )
               ) >= 2
           AND (SELECT COUNT(*) FROM product_attribute_value v
                 WHERE v.attribute_id = pa.id) <= 4
        """
    )

    return [row[0] for row in cr.fetchall()]


def _remove_attribute(cr, attribute):
    """Delete one trim attribute, its values and its product lines."""
    cr.execute(
        "SELECT id FROM product_template_attribute_value WHERE attribute_id = %s",
        (attribute,),
    )
    ptav_ids = [row[0] for row in cr.fetchall()]

    if ptav_ids:
        cr.execute(
            """
            SELECT COUNT(*)
              FROM product_template_attribute_value_sale_order_line_rel rel
              JOIN sale_order_line sol ON sol.id = rel.sale_order_line_id
              JOIN sale_order so ON so.id = sol.order_id
             WHERE rel.product_template_attribute_value_id = ANY(%s)
               AND so.state != 'draft'
            """,
            (ptav_ids,),
        )

        if cr.fetchone()[0]:
            _logger.warning(
                "Trims: a confirmed order records a trim colour, so attribute"
                " %s was left in place. Remove it by hand if you want it gone.",
                attribute,
            )

            return False

        cr.execute(
            """
            DELETE FROM product_template_attribute_value_sale_order_line_rel
             WHERE product_template_attribute_value_id = ANY(%s)
            """,
            (ptav_ids,),
        )
        cr.execute(
            "DELETE FROM product_template_attribute_value WHERE id = ANY(%s)",
            (ptav_ids,),
        )

    cr.execute(
        "DELETE FROM product_template_attribute_line WHERE attribute_id = %s",
        (attribute,),
    )
    cr.execute(
        "DELETE FROM product_attribute_value WHERE attribute_id = %s", (attribute,)
    )
    cr.execute("DELETE FROM product_attribute WHERE id = %s", (attribute,))

    return True


def migrate(cr, version):
    if not version:
        return

    removed = 0

    for attribute in _orphan_trim_attributes(cr):
        if _remove_attribute(cr, attribute):
            removed += 1

    attribute = _res_id(cr, "attribute_trim_colour")

    if not attribute:
        if removed:
            _logger.info("Trims: removed %s orphaned attribute(s).", removed)

        return

    if not _remove_attribute(cr, attribute):
        return

    cr.execute(
        "DELETE FROM ir_model_data WHERE module = %s AND name = ANY(%s)",
        (MODULE, list(NAMES)),
    )
    _logger.info(
        "Trims: attribute removed from all products (%s orphan(s) too).", removed
    )
