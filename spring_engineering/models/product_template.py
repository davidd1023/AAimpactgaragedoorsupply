from odoo import api, models

# A product is a vertical track if its name says so. The category would be a
# steadier signal, but the live track products were created by hand and their
# category cannot be relied on, whereas every one of them is named
# "... Vertical Track <length>-<height> door height <finish>".
VERTICAL_TRACK = "vertical track"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _attach_track_preparation(self):
        """Put the Prepared/Unprepared choice on every vertical track.

        WHY THIS IS AUTOMATIC. The module used to create the attribute and stop
        there, which meant the option appeared on nothing until someone opened
        each of the track products and added it by hand. The owner merged the
        code, looked at a track, and quite reasonably reported the feature
        missing - it was, on every product.

        Called from data/track_prep_data.xml on install AND on every update, so
        a track added later picks it up the next time the module is updated. It
        only ever ADDS: a track that already has the attribute is left alone,
        and nothing is removed, so running it twice is the same as running it
        once.
        """
        attribute = self.env.ref(
            "spring_engineering.attribute_track_preparation", raise_if_not_found=False
        )

        if not attribute:
            return

        values = (
            self.env.ref("spring_engineering.attribute_value_track_unprepared",
                         raise_if_not_found=False)
            | self.env.ref("spring_engineering.attribute_value_track_prepared",
                           raise_if_not_found=False)
        )

        if len(values) != 2:
            return

        tracks = self.with_context(active_test=False).search(
            [("name", "ilike", VERTICAL_TRACK)]
        )
        lines = self.env["product.template.attribute.line"]

        for track in tracks:
            if track.attribute_line_ids.filtered(
                lambda line: line.attribute_id == attribute
            ):
                continue

            lines.create({
                "product_tmpl_id": track.id,
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, values.ids)],
            })
