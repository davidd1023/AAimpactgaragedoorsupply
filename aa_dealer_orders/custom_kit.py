"""THE CUSTOM KIT: a kit the customer puts together themselves.

The owner, 2026-10-20: "customer can decide almost everything and can add and
remove things from their kit, no spring, tracks, or cables will be in the kit
... the trims will be included ... so that we can serve customers that want
doors that we dont have kits for."

IT IS A REAL KIT, NOT A SPECIAL CASE. The word "kit" in the product's name is
what the rest of this shop keys off: the trim attribute attaches itself to it,
the Hardware station raises a "Pack hardware kit" job for it, the sticker and
the customer emails treat it like any other box. Two matchers that said
"hardware kit" now also say "custom kit", which was cheaper than teaching four
modules about a new kind of product.

WHAT MAKES IT DIFFERENT, and the one thing that could not be reused: an
ordinary kit's contents are a phantom BoM fixed per variant, and a custom
kit's contents are different on every order. So the parts are booked as their
own order lines, hung off the kit line - which is exactly how Springs, Tracks,
Cables and Trims already reach a cart from the kit page. Nothing new is
invented: the kit line is the heading, each part is a line with its own
quantity and its own price (owner's choice, 2026-10-20), and the picker,
the delivery and the pricelists all work because every part is a real product.

NO SPRINGS, TRACKS OR CABLES. Those are sized from a door and sold against
one; a custom kit exists precisely because the door is not one we have a kit
for, so the page does not offer them and the Add to Your Order options are not
on this product.

PER-PART COLOUR (owner's choice, 2026-10-20). Which is honest here rather than
clever: some of these products carry a finish attribute and some have the
colour in their name, so a part is offered with the colours IT has - its own
variants where it has them, and otherwise as the product it is.
"""

import json

from odoo import api, fields, models

# What a finish attribute can be called. The same four spellings the hardware
# card reads, because the catalogue was not all built on one day.
COLOUR_ATTRIBUTES = ("finish color", "finish colour", "color", "colour")

# Never offered in a custom kit, whatever anybody ticks: these are sized from a
# door and sold against one (owner, 2026-10-20).
NEVER_IN_A_CUSTOM_KIT = ("spring", "track", "cable")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    aa_custom_kit = fields.Boolean(
        string="Custom Kit page",
        help="Show the build-your-own-kit page on this product, instead of the "
             "fixed door options the AA kits use.")
    aa_custom_kit_part = fields.Boolean(
        string="Offer in Custom Kit",
        help="Let a customer put this product in a custom kit. Nothing appears "
             "on that page until it is ticked here, so odd or obsolete stock "
             "stays off it.")

    # --- what the page is allowed to offer -------------------------------------

    @api.model
    def _aa_custom_kit_parts(self):
        """Every product a customer may put in a custom kit.

        TICKED, SALEABLE, AND NOT A SPRING, TRACK OR CABLE. The last of those
        is enforced here rather than left to whoever does the ticking, because
        a custom kit that quietly contained a track would be sized against a
        door nobody asked about.
        """
        parts = self.sudo().search([
            ("aa_custom_kit_part", "=", True),
            ("sale_ok", "=", True),
        ], order="categ_id, name")

        return parts.filtered(lambda part: not any(
            word in (part.name or "").lower() for word in NEVER_IN_A_CUSTOM_KIT))

    def _aa_custom_kit_colours(self):
        """[(variant id, label)] - the finishes this part comes in.

        ITS OWN VARIANTS WHERE IT HAS THEM. A product with a Finish Color
        attribute offers its colours; one whose colour is in its name is
        offered as the product it is, because that is what it is - there is no
        guessing at which products are secretly the same part in two colours.
        """
        self.ensure_one()
        variants = self.sudo().product_variant_ids

        if len(variants) <= 1:
            return [(variants[:1].id, "")] if variants else []

        colours = []

        for variant in variants:
            finish = variant.product_template_attribute_value_ids.filtered(
                lambda value: (value.attribute_id.name or "").strip().lower()
                in COLOUR_ATTRIBUTES)
            colours.append((variant.id, finish[:1].name or
                            ", ".join(variant.product_template_attribute_value_ids
                                      .mapped("name"))))

        return colours

    def _aa_custom_kit_json(self):
        """Everything the page needs, as data: the parts and the kits to start from."""
        self.ensure_one()
        parts = []

        for part in self._aa_custom_kit_parts():
            colours = part._aa_custom_kit_colours()

            if not colours:
                continue

            parts.append({
                "template_id": part.id,
                "name": part.name,
                "code": part.default_code or "",
                # THE PAGE IS SPLIT UP BY THIS (owner, 2026-10-20: "one list
                # for hinges, one for shafts"). The id does the grouping and
                # the name is only the heading, because two categories under
                # different parents can share a name.
                "category_id": part.categ_id.id,
                "category": part.categ_id.name or "",
                "price": round(part.list_price, 2),
                "colours": [{"id": variant_id, "label": label}
                            for variant_id, label in colours],
            })

        return json.dumps({
            "parts": parts,
            "bases": self._aa_custom_kit_bases(),
            "currency": self.env.company.currency_id.symbol or "",
        })

    # --- the kits a custom one can start from ---------------------------------

    @api.model
    def _aa_custom_kit_bases(self):
        """[{id, name, parts: {variant id: quantity}}] - a kit's real contents.

        READ OFF THE KIT'S OWN PHANTOM BoM, which is the only honest source:
        it is what the picker takes out of stock for that kit today. A kit
        whose BoM nobody has built yet offers an empty start rather than a
        guess, and says so on the page.
        """
        kits = self.sudo().search([
            ("aa_dealer_quick_order", "=", True),
            ("aa_custom_kit", "=", False),
        ], order="name")
        bases = []

        for kit in kits:
            variant = kit.product_variant_ids[:1]

            if not variant:
                continue

            bom = self.env["mrp.bom"].sudo()._bom_find(
                variant, bom_type="phantom").get(variant)
            parts = {}

            if bom:
                for line in bom.bom_line_ids:
                    if any(word in (line.product_id.name or "").lower()
                           for word in NEVER_IN_A_CUSTOM_KIT):
                        continue

                    quantity = line.product_qty / (bom.product_qty or 1.0)
                    parts[str(line.product_id.id)] = \
                        parts.get(str(line.product_id.id), 0.0) + quantity

            bases.append({"id": kit.id, "name": kit.name, "parts": parts})

        return bases
