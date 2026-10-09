from odoo import api, models

# A product is a vertical track if its name says so. The category would be a
# steadier signal, but the live tracks were created by hand and their
# categories cannot be relied on, whereas the names are consistent:
# "... Vertical Track 76" - 7' Door Height Black".
VERTICAL_TRACK = "vertical track"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _attach_option(self, attribute_ref, value_refs, name_fragment):
        """Put one no-variant option on every product whose name matches.

        WHY THIS IS AUTOMATIC. Creating an attribute puts it on nothing. The
        first version of the prepared-track feature did exactly that, and the
        option appeared on no product at all until someone opened each one and
        added it by hand - which, across a hundred tracks, was never a
        reasonable thing to ask. The owner merged it, looked at a track, and
        quite reasonably reported the feature missing.

        Called from the data files on install AND on every module update, so a
        product added later picks the option up at the next update. It only
        ever ADDS: a product that already has the attribute is skipped and
        nothing is removed, so running it twice is the same as running it once.
        """
        attribute = self.env.ref(attribute_ref, raise_if_not_found=False)

        if not attribute:
            return

        values = self.env["product.attribute.value"]

        for ref in value_refs:
            values |= self.env.ref(ref, raise_if_not_found=False) or values

        if len(values) != len(value_refs):
            return

        products = self.with_context(active_test=False).search(
            [("name", "ilike", name_fragment)]
        )
        lines = self.env["product.template.attribute.line"]

        for product in products:
            if product.attribute_line_ids.filtered(
                lambda line: line.attribute_id == attribute
            ):
                continue

            lines.create({
                "product_tmpl_id": product.id,
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, values.ids)],
            })

    @api.model
    def _attach_track_preparation(self):
        """The Prepared/Unprepared choice, on every vertical track."""
        self._attach_option(
            "spring_engineering.attribute_track_preparation",
            (
                "spring_engineering.attribute_value_track_unprepared",
                "spring_engineering.attribute_value_track_prepared",
            ),
            VERTICAL_TRACK,
        )
