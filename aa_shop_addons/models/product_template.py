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
**Alternative Products** field, which is right by definition because he set it.

ALTERNATIVE, NOT ACCESSORY. This first read Accessory Products, which is
Odoo's cross-sell field and shows in the CART. Odoo's own help for Alternative
Products says "those products show up on the product page", which is where he
asked for these, and he has since had the other two boxes hidden so there is
one place to fill in rather than three that look alike (owner, 2026-10-27:
"we only want the alternative products choice"). It is a Many2many of
TEMPLATES rather than variants, which is also what this shows.

THEN HE ASKED FOR IT WITHOUT THE TYPING (2026-10-27): *"could you automate a
system that will recommend additional products the same way that the
alternative product thing works. this way i wont have to individually go into
every products page."* So there are now THREE tiers, in this order:

  1. WHAT HE PICKED, if he picked anything. Unchanged, and still right by
     definition.
  2. WHAT HIS OWN ORDERS SAY, counted from `sale_order_line` - see
     `addon_suggestion.py`. Not a rule about garage doors: a rule about his
     shop. It cannot recommend something nobody has bought alongside, which
     is exactly why it can be trusted with a page nobody has reviewed.
  3. THE FAMILIES, as before.

THE FAMILIES ARE THE LAST FALLBACK. A kit nobody has got to AND nobody has
bought twice shows the right KINDS - here are the cables, here are the tracks -
rather than an empty space under it. That way the page is never blank and never
wrong, it is just less specific until either he or the order book makes it
specific.

TEMPLATES ARE SHOWN, NOT VARIANTS. A track is one product with twenty
length-and-colour combinations behind it (the catalogue merge, 2026-10-21), so
listing variants would put twenty near-identical cards under a kit. One card
leads to the page where the choice is made.
"""

from odoo import api, fields, models

#: The families, in the order they read under a product. Cones first because
#: on a spring page they carry a warning rather than an invitation.
FAMILIES = [
    ("cones", "Cones"),
    ("cables", "Cables"),
    ("tracks", "Tracks"),
    ("trims", "Trims"),
]

SETTING = "aa_shop_addons.category_%s"

#: THE CATEGORY THAT MARKS A KIT, and it had to become a setting like the
#: other four. His live catalogue has four kits - AA-1200, AA-1600, AA-1800
#: and AA-Custom - in the WEBSITE category "Hardware Kits", and not one of
#: them carries an `HK-` part number. The twelve `HK-<series>-<panels>P`
#: products this was written against are not what the shop sells.
KIT_SETTING = "aa_shop_addons.category_kits"

#: What a kit calls itself, wherever it says so. Matched as a substring, so
#: "Hardware Kit" and "Hardware Kits" both count.
KIT_WORDS = "hardware kit"

#: How many to show, in ONE pool (owner, 2026-10-27: "just one pool of
#: products not multiple categories, that way we dont show too many products
#: in the recommendations"). Eight is two rows of four on a desktop and four
#: rows of two on a telephone.
SHOWN = 8
SHOWN_SETTING = "aa_shop_addons.shown"

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
        """"kit", "spring", or False for everything else."""
        self.ensure_one()

        spring = self.env.ref(
            "spring_engineering.product_custom_spring", raise_if_not_found=False)

        if spring and spring == self:
            return "spring"

        return "kit" if self._aa_is_kit() else False

    def _aa_is_kit(self):
        """Does this product say, anywhere, that it is a hardware kit?

        FOUR MARKS, AND THE FIRST ONE ALONE WAS WRONG. This shipped looking
        for an `HK-<series>-<panels>P` part number, because that is what
        `garage_door_supply/hooks.py` creates. HIS SHOP DOES NOT SELL THOSE.
        The live catalogue has four kits - AA-1200, AA-1600, AA-1800 and
        AA-Custom - in the website category "Hardware Kits", so the block
        drew nothing on any of them and he quite reasonably reported that the
        feature did not work (owner, 2026-10-27: "i dont see the recommended
        products under the kits").

        So: the website category he can point at in Settings, then the word
        itself in either category or in the product's own name, then the SKU
        last. A product that says "Hardware Kit" in its name is a hardware
        kit; refusing to read the name and demanding a part number instead
        was the mistake.
        """
        self.ensure_one()

        chosen = self._aa_kit_category()

        if chosen and chosen in self.public_categ_ids:
            return True

        said = [self.name or "", self.categ_id.complete_name or ""]
        said += [category.name or "" for category in self.public_categ_ids]

        if any(KIT_WORDS in where.lower() for where in said):
            return True

        return (self.default_code or "").upper().startswith("HK-")

    @api.model
    def _aa_kit_category(self):
        """The website category that marks a kit, if one is set.

        A setting for the same reason as the other four: a name lookup is a
        guess, and the word check below covers the obvious names anyway, so
        this exists for a catalogue that calls them something else entirely.
        """
        chosen = self.env["ir.config_parameter"].sudo().get_param(KIT_SETTING)

        if not chosen:
            return self.env["product.public.category"]

        try:
            return self.env["product.public.category"].sudo().browse(
                int(chosen)).exists()
        except (TypeError, ValueError):
            return self.env["product.public.category"]

    @api.model
    def _aa_addon_category(self, key, label):
        """The website category a family falls back to.

        A setting first, because a name lookup is a guess and a guess that
        cannot be corrected without a deploy is a bad guess.

        THE NAME MATCH IS NOT EXACT, and that is from his own catalogue. It
        was `=ilike "Cables"`, and his live site has no category by that name
        - nor Cones, nor Trims. Only Tracks matched, out of four. So the
        exact name is tried first, then the word on its own: "Cables" finds
        "Lift Cables", and "Trims" dropped to "trim" finds "Trim" singular.
        The setting is still the last word for a category called something
        that shares no word at all.
        """
        categories = self.env["product.public.category"].sudo()
        chosen = self.env["ir.config_parameter"].sudo().get_param(SETTING % key)

        if chosen:
            try:
                found = categories.browse(int(chosen)).exists()
            except (TypeError, ValueError):
                found = categories

            if found:
                return found

        exact = categories.search([("name", "=ilike", label)], limit=1)

        if exact:
            return exact

        for word in (label, label.rstrip("sS")):
            loose = categories.search([("name", "ilike", word)], limit=1)

            if loose:
                return loose

        return categories

    def _aa_addon_source(self):
        """("picked" | "learned" | "families", the products or None).

        THE ORDER IS THE WHOLE DESIGN. His own pick first, because he said so.
        Then what his orders have been saying all year, which is the automatic
        part he asked for. Then the families, which are never wrong and never
        specific.
        """
        self.ensure_one()

        # WHETHER HE CHOSE, NOT WHETHER THE CHOICE SURVIVED. A kit with one
        # product set that happens to be unpublished has still been got to,
        # and falling back there would answer his one deliberate pick with
        # every cable in the catalogue. The fallback is for an EMPTY field.
        if self.alternative_product_ids:
            return "picked", self.alternative_product_ids.filtered(
                lambda product: product.is_published
                and product.id != self.id)

        learned = self.env["aa.addon.suggestion"]._aa_for(self)

        if learned:
            return "learned", learned

        return "families", None

    def _aa_addon_picks(self):
        """{products, note} - ONE POOL, not a heading per family.

        Owner, 2026-10-27: *"i want the recommendations to be just one pool of
        products not multiple categories, that way we dont show too many
        products in the recommendations."*

        It was four headings with up to eight products under each, which on a
        kit page was a second catalogue rather than a recommendation. Now it
        is one short row, capped by a setting, and the families do nothing but
        decide what is eligible.

        Empty for anything that is not a kit or a spring, and for a kit with
        nothing to show - the block draws nothing rather than a heading with
        an empty space under it.
        """
        self.ensure_one()
        role = self._aa_addon_role()

        if not role:
            return {}

        source, picked = self._aa_addon_source()
        shown = self._aa_addon_shown()
        products = picked[:shown] if picked is not None else self._aa_family_pool(shown)

        if not products:
            return {}

        return {
            "source": source,
            "products": products,
            "note": self._aa_cones_note(role, products),
        }

    @api.model
    def _aa_addon_shown(self):
        """How many to show. A setting, because "too many" is his judgement
        and not a number to need a deploy for."""
        raw = self.env["ir.config_parameter"].sudo().get_param(SHOWN_SETTING)

        if not raw:
            return SHOWN

        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return SHOWN

    def _aa_family_pool(self, shown):
        """The last fallback, TAKEN IN TURNS ROUND THE FAMILIES.

        This is the one place where flattening four lists into one needs care.
        Taken in sequence, a pool of eight off a catalogue like his would be
        eight cones and nothing else - every cable, track and trim pushed off
        the end by whichever family happened to be listed first. So one is
        taken from each family in turn until the pool is full, which gives a
        spread of what a customer might still need. That is the whole point of
        a fallback: not specific, but never silly.
        """
        self.ensure_one()
        queues = []

        for key, label in FAMILIES:
            category = self._aa_addon_category(key, label)

            if not category:
                continue

            found = self.env["product.template"].search([
                ("public_categ_ids", "child_of", category.id),
                ("is_published", "=", True),
                ("id", "!=", self.id),
            ], limit=shown)

            if found:
                queues.append(list(found))

        pool = self.env["product.template"]
        taken = True

        while taken and len(pool) < shown:
            taken = False

            for queue in queues:
                if not queue or len(pool) >= shown:
                    continue

                product = queue.pop(0)
                taken = True

                if product not in pool:
                    pool |= product

        return pool

    def _aa_cones_note(self, role, products):
        """The cones warning, now that there is no Cones heading to hang it on.

        Owner, 2026-10-27: *"show them but make it obvious that the cones are
        included so customers dont make the mistake of buying when they dont
        need one."* The calculator prices the cone set for the chosen I.D.
        into the spring itself, so a customer configuring one is already
        buying cones.

        It hung off the Cones group before. With one pool it has to ask
        whether a cone is actually in what is being shown - and it asks by
        category OR by name, because his live catalogue has no Cones category
        at all and a warning that never appears is worse than one that
        occasionally appears beside a cone wrench.
        """
        if role != "spring":
            return ""

        category = self._aa_addon_category("cones", "Cones")

        for product in products:
            if category and category in product.public_categ_ids:
                return CONES_INCLUDED

            if "cone" in (product.name or "").lower():
                return CONES_INCLUDED

        return ""

    # --- "why do I not see them" ------------------------------------------

    aa_addon_summary = fields.Char(
        string="Will show", compute="_compute_aa_addon_summary",
        help="What the add-ons block under this product would draw right now.")

    @api.depends("alternative_product_ids")
    def _compute_aa_addon_summary(self):
        """ONE LINE SAYING WHAT THE PAGE WILL DO, AND WHERE IT CAME FROM.

        This exists because answering "i dont see the recommended products
        under the kits" took crawling his live website to discover that his
        kits are not called what this module expected. That is not a way to
        answer the same question twice.
        """
        for product in self:
            role = product._aa_addon_role()

            if not role:
                product.aa_addon_summary = "No block - not read as a kit"
                continue

            picks = product._aa_addon_picks()

            if not picks:
                product.aa_addon_summary = (
                    "Nothing to show - no add-on products were found")
                continue

            where = {
                "picked": "you picked these",
                "learned": "from your orders",
                "families": "a spread of the families - nothing picked,"
                            " nothing counted",
            }[picks["source"]]

            product.aa_addon_summary = "%s products (%s)" % (
                len(picks["products"]), where)

    @api.model
    def action_aa_addon_check(self):
        """Every product that gets a block, and what it will draw."""
        subjects = self.env["aa.addon.suggestion"]._aa_subjects()

        return {
            "type": "ir.actions.act_window",
            "name": "Add-ons Check",
            "res_model": "product.template",
            "view_mode": "list",
            "views": [(self.env.ref(
                "aa_shop_addons.view_product_addon_check_list").id, "list")],
            "domain": [("id", "in", subjects.ids)],
            "context": {"create": False},
            "help": """
                <p class="o_view_nocontent_smiling_face">No product is read as
                   a kit or a spring</p>
                <p>Nothing on the site will show an add-ons block. A product is
                   read as a kit when its name, its product category or one of
                   its website categories says "Hardware Kit" - or when you
                   point at the right website category under Website &gt;
                   Configuration &gt; Settings &gt; Garage Door Add-ons.</p>
            """,
        }

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
