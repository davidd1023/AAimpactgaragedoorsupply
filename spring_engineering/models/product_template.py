from odoo import api, models

from .sale_order import PREPARED

# A product is a vertical track if its name says so, and a hardware kit the
# same way. The category would be a steadier signal, but the live products
# were created by hand and their categories cannot be relied on, whereas the
# names are consistent: "... Vertical Track 76" - 7' Door Height Black" and
# "AA 1200 Hardware Kit".
VERTICAL_TRACK = "vertical track"
HARDWARE_KIT = "hardware kit"


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

    @api.model
    def _attach_trim_colour(self):
        """The trim colour, on every hardware kit.

        WHY AN ATTRIBUTE AND NOT THE JAVASCRIPT THIS REPLACES. The first
        attempt hooked Odoo's "Custom value" text box - the thing that makes
        the other extras on a kit page open a square to type in - and swapped
        it for a dropdown. It never worked on the live site, because it needed
        the existing Trims value flagged as a custom value by hand, and because
        it shipped in a module that site does not install.

        The attribute route is the one that demonstrably works: the prepared
        track option reached the live site by exactly this path. The choice
        also lands on the order line by itself, with no code to collect it.
        """
        self._attach_option(
            "spring_engineering.attribute_trim_colour",
            (
                "spring_engineering.attribute_value_trim_none",
                "spring_engineering.attribute_value_trim_black",
                "spring_engineering.attribute_value_trim_bronze",
                "spring_engineering.attribute_value_trim_white",
            ),
            HARDWARE_KIT,
        )

    # --- what a prepared track costs, before anything is in a cart ----------

    def _track_prep_extra(self, combination, product_id, add_qty=1.0):
        """What preparing one of these tracks adds to its price, or 0.0.

        THE SHOP PAGE HAS TO SAY THE SAME THING THE CART WILL CHARGE. Picking
        Prepared adds a flag angle and a graduated set of jamb brackets to the
        order - the attribute itself carries no price_extra, because the parts
        are real products billed on their own lines - so the page went on
        showing the bare track's price and the total only grew at the cart.
        That reads as a surprise charge, which is the one thing a price on a
        product page must never be.

        PRICED THROUGH THE PARTS' OWN PAGE PRICE, not from their list price:
        each part is asked for its combination info the same way the shop asks
        for any product, so the dealer's pricelist, the fiscal position and the
        tax display setting all apply exactly as they will when the lines are
        booked. A quantity break on a part is honoured for the number of them
        this many tracks need.
        """
        if self.env.context.get("track_prep_no_extra"):
            return 0.0

        if not combination or not any(
            (value.name or "").strip().lower() == PREPARED for value in combination
        ):
            return 0.0

        product = self.env["product.product"].browse(product_id) if product_id else self
        wanted, warning = self.env["sale.order"]._track_prep_requirements(product)

        # A track this cannot prepare adds nothing in the cart either, and the
        # cart says why. Showing an inflated price for parts that will not be
        # added would be worse than showing the bare one.
        if warning:
            return 0.0

        extra = 0.0

        for part, count in wanted.values():
            info = part.product_tmpl_id.with_context(
                track_prep_no_extra=True
            )._get_combination_info(
                product_id=part.id, add_qty=count * (add_qty or 1.0)
            )
            extra += info["price"] * count

        return extra

    def _get_combination_info(
        self, combination=False, product_id=False, add_qty=1.0, uom_id=False,
        only_template=False,
    ):
        """The shop's price for a combination, with the preparation in it."""
        info = super()._get_combination_info(
            combination=combination, product_id=product_id, add_qty=add_qty,
            uom_id=uom_id, only_template=only_template,
        )

        if only_template:
            return info

        extra = self._track_prep_extra(
            info.get("combination"), info.get("product_id"), add_qty)

        if not extra:
            return info

        for key in ("price", "list_price"):
            if key in info:
                info[key] += extra

        # The comparison price is a figure the owner typed, shown as it is - but
        # comparing a prepared track against an unprepared list price would
        # overstate the saving, so it moves with the rest.
        if info.get("compare_list_price"):
            info["compare_list_price"] += extra

        return info
