"""WHICH EXTRAS BELONG UNDER A KIT OR A SPRING, AND WHO DECIDES.

Owner, 2026-10-27: *"On every kit and spring page, show the matching add-ons
(cones, cables, tracks, trims) below the product. Done when: each kit shows
its correct add-ons."*

THE HARD PART IS "CORRECT", AND IT IS NOT A RULE. A hardware kit knows two
things about itself: its series and how many panels it is for. What picks one
cable out of twelve is the door height and the drum; what picks one track is
the height, the track size and the colour; what picks a trim is the colour.
None of those are on the kit. Asked whether to guess them, show the families,
or let him choose, the owner chose to choose - so the list is Odoo's own
Accessory Products field, which is right by definition because he set it.

THE FAMILIES ARE THE FALLBACK. A kit he has not got to yet shows the right
KINDS - here are the cables, here are the tracks - rather than an empty space
under it. That way the page is never blank and never wrong, it is just less
specific until somebody makes it specific.

TEMPLATES ARE SHOWN, NOT VARIANTS. A track is one product with twenty
length-and-colour combinations behind it (the catalogue merge, 2026-10-21), so
listing variants would put twenty near-identical cards under a kit. One card
leads to the page where the choice is made.
"""

from odoo import api, models

#: The families, in the order they read under a product. Cones first because
#: on a spring page they carry a warning rather than an invitation.
FAMILIES = [
    ("cones", "Cones"),
    ("cables", "Cables"),
    ("tracks", "Tracks"),
    ("trims", "Trims"),
]

SETTING = "aa_shop_addons.category_%s"

#: How many to show per family before pointing at the rest.
SHOWN = 8

#: Set on the SPRING page only. His calculator prices the cone set for the
#: chosen I.D. into the spring itself, at cost - so a customer configuring a
#: spring is already buying cones, and a row of them underneath reads as
#: something missing. Owner, 2026-10-27, asked whether to drop them: "show
#: them but make it obvious that the cones are included so customers dont make
#: the mistake of buying when they dont need one".
CONES_INCLUDED = (
    "Already included with your spring. You only need these if you are"
    " replacing the cones on a spring you already have."
)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _aa_addon_role(self):
        """"kit", "spring", or False for everything else.

        A kit is known by its part number - every one of them is HK-<series>-
        <panels>P (garage_door_supply/hooks.py) - or by sitting in a category
        that says Hardware Kit. Two marks rather than one, because a kit
        added by hand later may well not follow the SKU.
        """
        self.ensure_one()

        spring = self.env.ref(
            "spring_engineering.product_custom_spring", raise_if_not_found=False)

        if spring and spring == self:
            return "spring"

        code = (self.default_code or "").upper()

        if code.startswith("HK-"):
            return "kit"

        where = self.categ_id.complete_name or ""

        if "hardware kit" in where.lower():
            return "kit"

        return False

    @api.model
    def _aa_addon_category(self, key, label):
        """The website category a family falls back to.

        A setting first, because a name lookup is a guess and a guess that
        cannot be corrected without a deploy is a bad guess. The name is what
        it falls back to, so this works out of the box on a catalogue whose
        categories are called the obvious thing.
        """
        categories = self.env["product.public.category"].sudo()
        chosen = self.env["ir.config_parameter"].sudo().get_param(SETTING % key)

        if chosen:
            found = categories.browse(int(chosen)).exists()

            if found:
                return found

        return categories.search([("name", "=ilike", label)], limit=1)

    def _aa_addon_groups(self):
        """[{key, label, note, products, category}] to show under this page.

        Empty for anything that is not a kit or a spring, and for a kit whose
        families are all empty - the block draws nothing rather than a row of
        headings with nothing under them.
        """
        self.ensure_one()
        role = self._aa_addon_role()

        if not role:
            return []

        # WHETHER HE CHOSE, NOT WHETHER THE CHOICE SURVIVED. A kit with one
        # accessory set that happens to be unpublished has still been got to,
        # and falling back there would answer his one deliberate pick with
        # every cable in the catalogue. The fallback is for an EMPTY field.
        chosen = self.accessory_product_ids
        picked = chosen.product_tmpl_id.filtered(
            lambda product: product.is_published)
        groups = []

        for key, label in FAMILIES:
            category = self._aa_addon_category(key, label)

            if not category:
                continue

            if chosen:
                # HIS CHOICE, SORTED INTO FAMILIES. The grouping is by the
                # website category the product is already in, so adding an
                # accessory never also means saying which heading it goes
                # under.
                products = picked.filtered(lambda p: category in p.public_categ_ids)
            else:
                products = self.env["product.template"].search([
                    ("public_categ_ids", "child_of", category.id),
                    ("is_published", "=", True),
                    ("id", "!=", self.id),
                ], limit=SHOWN + 1)

            if not products:
                continue

            groups.append({
                "key": key,
                "label": label,
                "note": CONES_INCLUDED if (key == "cones" and role == "spring")
                        else "",
                "products": products[:SHOWN],
                "more": len(products) > SHOWN,
                "category": category,
            })

        # ANYTHING HE PICKED THAT IS IN NONE OF THE FAMILIES still belongs on
        # the page. Dropping it silently would make the field lie: he set an
        # accessory and the page did not show it.
        if chosen:
            placed = self.env["product.template"]

            for group in groups:
                placed |= group["products"]

            rest = picked - placed

            if rest:
                groups.append({
                    "key": "other",
                    "label": "Also needed",
                    "note": "",
                    "products": rest[:SHOWN],
                    "more": len(rest) > SHOWN,
                    "category": False,
                })

        return groups

    def _aa_addon_price(self):
        """What to print under an add-on's name, honouring the pricelist.

        Best effort: a price that cannot be worked out is left off rather
        than guessed at or shown as zero, which would read as free.
        """
        self.ensure_one()

        try:
            combination = self.sudo()._get_combination_info(only_template=True)
            return combination.get("price")
        except Exception:      # noqa: BLE001 - a missing price is not a 500
            return None
