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
import re

from odoo import api, fields, models

# What a finish attribute can be called. The same four spellings the hardware
# card reads, because the catalogue was not all built on one day.
COLOUR_ATTRIBUTES = ("finish color", "finish colour", "color", "colour")

# Never offered in a custom kit, whatever anybody ticks: these are sized from a
# door and sold against one (owner, 2026-10-20).
NEVER_IN_A_CUSTOM_KIT = ("spring", "track", "cable")

# THE FINISHES THIS TRADE SELLS, longest first so "desert tan" is read as one
# colour and not as "tan". Used to recognise that two products are the same
# part in two colours - which is how this catalogue is built, there being no
# finish attribute on a hinge - and nothing is grouped unless a sibling with
# the same name in another colour is actually there to group it with.
COLOUR_WORDS = (
    "desert tan", "sandstone", "terratone", "chocolate", "galvanized",
    "galvanised", "almond", "bronze", "walnut", "wicker", "silver", "copper",
    "primed", "white", "black", "brown", "clay", "gray", "grey", "zinc",
    "tan",
)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _verify_updated_quantity(self, order_line, product_id, new_qty, uom_id, **kwargs):
        """A KIT'S PARTS ARE BUILT TO ORDER, so the shop's out-of-stock rule
        does not apply to them.

        THE FAULT THIS FIXES, 2026-10-20: the owner built a 13-part kit, the
        page priced it at $236.91, he added it to the cart and got the kit by
        itself. The parts WERE sent, stored and read back - and then dropped
        one by one, here.

        website_sale_stock refuses a storable product that is not in stock:
        "%s has not been added to your cart since it is not available", with
        the quantity clamped to zero and no line created. Every part of that
        kit is a part AA Impact fits to order rather than keeps on a shelf, so
        every one of them was refused. The one hinge that did get through on
        an earlier attempt was the one with stock on hand, which is what made
        it look as if the list were being lost.

        THE RULE IS NOT REMOVED, it is scoped: it still applies to anything a
        customer buys on its own. It is passed over only for lines this
        module's kit pages book as the contents of a kit, which is how a
        phantom-BoM kit already behaves - nobody is stopped from ordering an
        AA 1200 because a hinge inside it shows zero.
        """
        if self.env.context.get("aa_kit_parts"):
            return new_qty, ""

        return super()._verify_updated_quantity(
            order_line, product_id, new_qty, uom_id, **kwargs)


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
        # BY NAME, because the shelving no longer follows the internal
        # category and this is the order the parts appear in within a shelf.
        parts = self.sudo().search([
            ("aa_custom_kit_part", "=", True),
            ("sale_ok", "=", True),
        ], order="name")

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
            values = variant.product_template_attribute_value_ids
            finish = values.filtered(
                lambda value: (value.attribute_id.name or "").strip().lower()
                in COLOUR_ATTRIBUTES)

            # EVERY OTHER CHOICE GOES IN THE LABEL TOO, or the list cannot be
            # read. Since the catalogue's colours and sizes were folded into
            # one product each (owner, 2026-10-21) a hinge is ONE product with
            # 21 variants, and labelling them by finish alone offered the
            # dealer "Black" seven times over - whereupon picking Black got
            # him whichever SIZE happened to come first. "#3 Black" says which
            # one he is choosing. A part that only comes in colours reads
            # exactly as it did before.
            others = values - finish
            label = " ".join(part for part in (
                ", ".join(others.mapped("name")),
                finish[:1].name or "",
            ) if part)

            colours.append((variant.id,
                            label or ", ".join(values.mapped("name"))))

        return colours

    def _aa_custom_kit_shelf(self):
        """(key, label) - which of the page's lists this part belongs on.

        THE SHOP'S OWN CATEGORY FIRST, the internal Product Category second.
        Which matters more than it sounds: in Odoo 19 `categ_id` is neither
        required nor given a default, so a catalogue built through the website
        can have every single product in no internal category at all - and
        that is how the owner came to see every part he ticked land on one
        "Other parts" shelf (2026-10-20: "they each have categories that
        should be used to split them into the correct groups"). The categories
        he means are the ones the shop is arranged by.

        A part in several shop categories is shelved under the first of them,
        which is the one the shop itself puts first (sequence, then name).

        The key is prefixed because the two sources are different models and
        their ids collide: shop category 4 is not product category 4.
        """
        self.ensure_one()
        shop = self.sudo().public_categ_ids[:1]

        if shop:
            return "w%d" % shop.id, shop.name

        category = self.sudo().categ_id

        # A parentless "All" is Odoo's root shelf, not a category anybody
        # chose, so it is treated as none at all rather than printed.
        if category and (category.parent_id or category.name != "All"):
            return "c%d" % category.id, category.name

        return "none", "Other parts"

    def _aa_colour_in_name(self):
        """(what the part is, what colour it is) read off the product's name.

        WHY THIS EXISTS, 2026-10-20: the colour dropdown did not appear, and
        the reason is that nothing in this catalogue has a finish ATTRIBUTE.
        A white hinge and a black hinge are two separate products with the
        colour written in the name, so there was no part with two colours for
        the page to offer - and the parts a kit fills itself with were the
        white ones, which is what the owner was changing a row at a time.

        ("", "") is returned for a name that is only a colour, and for a
        product whose name holds no colour at all, which are both left alone.
        """
        self.ensure_one()
        name = (self.name or "").strip()

        for word in COLOUR_WORDS:
            found = re.search(r"\b%s\b" % re.escape(word), name, re.IGNORECASE)

            if not found:
                continue

            stem = "%s %s" % (name[:found.start()], name[found.end():])
            stem = re.sub(r"\s+", " ", stem).strip(" -,/()")

            return stem, found.group(0).title()

        return "", ""

    def _aa_custom_kit_build(self):
        """The installed version of this module - for staff, on the page.

        WHICH IS NOT TRIVIA, 2026-10-20: three faults in a row were reported
        against a build that did not have the code being discussed. Production
        carries whatever has been merged into it, a dev build carries whatever
        was last pushed, and nothing on the page said which. Now it does, to
        anybody signed in as staff and to nobody else.
        """
        self.ensure_one()

        if not self.env.user.has_group("base.group_user"):
            return ""

        module = self.env["ir.module.module"].sudo().search(
            [("name", "=", "aa_dealer_orders")], limit=1)

        return module.installed_version or ""

    def _aa_custom_kit_part_json(self, name, colours):
        """One row of the page: a part, under a name, in these colours."""
        self.ensure_one()

        # THE PAGE IS SPLIT UP BY THIS (owner, 2026-10-20: "one list for
        # hinges, one for shafts"). The key does the grouping and the name is
        # only the heading, because two categories under different parents can
        # share a name.
        shelf, shelf_name = self._aa_custom_kit_shelf()

        return {
            "template_id": self.id,
            "name": name,
            "code": self.default_code or "",
            "category_id": shelf,
            "category": shelf_name,
            "price": round(self.list_price, 2),
            "colours": [{"id": variant_id, "label": label}
                        for variant_id, label in colours],
        }

    def _aa_custom_kit_json(self):
        """Everything the page needs, as data: the parts and the kits to start from."""
        self.ensure_one()
        rows = []
        families = {}

        for part in self._aa_custom_kit_parts():
            colours = part._aa_custom_kit_colours()

            if not colours:
                continue

            stem, colour = part._aa_colour_in_name()

            # A part with real finish variants already offers them itself, and
            # a product with no colour in its name is just that product.
            if len(colours) > 1 or not colour or not stem:
                rows.append((part, part.name, colours))

                continue

            key = re.sub(r"[^a-z0-9]+", "", stem.lower())
            families.setdefault(key, {"stem": stem, "members": []})
            families[key]["members"].append((part, colour, colours[0][0]))

        parts = [part._aa_custom_kit_part_json(name, colours)
                 for part, name, colours in rows]

        for family in families.values():
            members = family["members"]

            # ONE PRODUCT PER COLOUR. A catalogue can hold the same name
            # twice, and a dropdown offering Galvanized, Galvanized and White
            # asks the customer a question with no answer.
            seen = {}

            for part, colour, variant_id in members:
                seen.setdefault(colour, variant_id)

            # ONE ROW, IN BOTH COLOURS, when the catalogue really does have
            # the same part twice: "11ga #8 Hinge White" and "... Black"
            # become "11ga #8 Hinge" with a colour to pick, which is also
            # half as many rows to read.
            if len(seen) > 1:
                parts.append(members[0][0]._aa_custom_kit_part_json(
                    family["stem"],
                    [(variant_id, colour) for colour, variant_id in seen.items()]))

                # AND NOTHING DISAPPEARS: a second product of a colour that is
                # already taken is still offered, under its own name.
                for part, colour, variant_id in members:
                    if seen[colour] != variant_id:
                        parts.append(part._aa_custom_kit_part_json(
                            part.name, [(variant_id, "")]))

                continue

            # A FAMILY OF ONE COLOUR IS NEVER RENAMED. There is nothing to
            # switch to, so "Zinc Plated Bolt" stays what it is called rather
            # than becoming a "Plated Bolt" that comes in zinc.
            for part, _colour, variant_id in members:
                parts.append(
                    part._aa_custom_kit_part_json(part.name, [(variant_id, "")]))

        parts.sort(key=lambda row: row["name"])

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
