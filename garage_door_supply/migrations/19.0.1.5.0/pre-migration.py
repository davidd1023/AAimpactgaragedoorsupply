"""Remove garage_door_supply's Track Preparation attribute; spring_engineering owns it now.

WHY. The prepared-vertical-track feature was built here and then moved to
spring_engineering, because the live site runs spring_engineering and may not
have garage_door_supply installed at all. Moving the XML records left this
module owning external IDs that are no longer in its data files, and Odoo
deletes those at the end of an update - but they were attached to real track
products, so the update died on a foreign key every time:

    update or delete on table "product_attribute_value" violates foreign key
    constraint ... on "product_attribute_value_product_template_attribute_line_rel"

WHAT THE DATABASE ACTUALLY LOOKED LIKE, which took four failed attempts to go
and read instead of guessing at:

    attribute 25, owned by garage_door_supply, values 108/109, attached to 3 tracks
    attribute 26, owned by spring_engineering, values 110/111, attached to the SAME 3

Two attributes both called "Track Preparation", both on every track, because
the attaching code ran for the new one while the old one's lines were already
there. Both were therefore in use, which is why the previous attempt - "delete
the duplicate only if nothing references it" - deleted neither and changed
nothing.

So the old one goes, lines and all. spring_engineering's copy is already in
place and already attached, so nothing needs handing over: this is a cleanup,
not a migration of ownership.

IT REFUSES TO RUN IF AN ORDER DEPENDS ON THE OLD VALUES. A quote that recorded
"Prepared" against attribute 25 would lose that information, so the script
stops and lets the update fail rather than quietly rewriting history. Nothing
has shipped on this attribute, so that branch should never be taken - but it is
the difference between a cleanup and data loss.

AND THE VERSION NUMBER MATTERS. A migration only runs when the manifest version
is HIGHER than the one recorded in ir_module_module. Three earlier attempts sat
in directories whose versions the failed updates had already written to the
database, so they were skipped in silence while the same error repeated.
"""

OLD_MODULE = "garage_door_supply"
NEW_MODULE = "spring_engineering"
NAMES = (
    "attribute_track_preparation",
    "attribute_value_track_unprepared",
    "attribute_value_track_prepared",
)


def _res_id(cr, module, name):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s",
        (module, name),
    )
    row = cr.fetchone()

    return row[0] if row else None


def migrate(cr, version):
    if not version:
        return

    old_attribute = _res_id(cr, OLD_MODULE, "attribute_track_preparation")

    if not old_attribute:
        return

    new_attribute = _res_id(cr, NEW_MODULE, "attribute_track_preparation")

    if not new_attribute or new_attribute == old_attribute:
        # Nothing has taken over, so removing this would take the feature with
        # it. Leave it alone.
        return

    # The template values that stand for the old attribute on each product.
    cr.execute(
        "SELECT id FROM product_template_attribute_value WHERE attribute_id = %s",
        (old_attribute,),
    )
    ptav_ids = [row[0] for row in cr.fetchall()]

    if ptav_ids:
        # Would any order lose what it recorded?
        cr.execute(
            """
            SELECT 1
              FROM product_template_attribute_value_sale_order_line_rel
             WHERE product_template_attribute_value_id = ANY(%s)
             LIMIT 1
            """,
            (ptav_ids,),
        )

        if cr.fetchone():
            return

        cr.execute(
            "DELETE FROM product_template_attribute_value WHERE id = ANY(%s)",
            (ptav_ids,),
        )

    cr.execute(
        "DELETE FROM product_template_attribute_line WHERE attribute_id = %s",
        (old_attribute,),
    )
    cr.execute(
        "DELETE FROM product_attribute_value WHERE attribute_id = %s", (old_attribute,)
    )
    cr.execute("DELETE FROM product_attribute WHERE id = %s", (old_attribute,))
    cr.execute(
        "DELETE FROM ir_model_data WHERE module = %s AND name = ANY(%s)",
        (OLD_MODULE, list(NAMES)),
    )
