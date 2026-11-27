"""THE RAW TRACK FAMILIES, READ OFF THE CATALOGUE (owner, 2026-11-27).

"crea variantes con todos los tracks raws de todas sus medidas al igual que
los terminados de 2" y 3"" - the RAW stock goes the way the prepared tracks
went on 2026-10-23: one product per size and type, the length and the finish
chosen on it. The owner said "Leave RAW alone" then; he has now asked for it.

FOUR FAMILIES, the same split as the prepared ones: 2" and 3", horizontal and
vertical. Assembled from whatever the catalogue holds rather than listed, for
the reasons in track_families.py - he adds lengths, and the RAW names are read
by a tested reader (_aa_raw_track_facts) already.

THE ATL PIECE IS A CHOICE ON THE SAME PRODUCT, NOT A PRODUCT OF ITS OWN.
Asked, the owner chose "Dentro del mismo producto". So a family with an ATL
member carries a third attribute, Line (CHI / ATL), and the CHI/ATL pairing
that used to be template to template (aa_line_twin_id) is now variant to
variant inside the one product - hw_line.py reads the Line value first.

THE LENGTH IS ITS OWN ATTRIBUTE, NOT THE PREPARED TRACK'S. A prepared track is
named by the length it is cut TO (96", "76" - 7' Door Height"); RAW stock by
the length it is BOUGHT at (9'6", 7'4"). Sharing one list would offer a RAW
horizontal at 96" and a prepared one at 9'6", neither of which exists.

THE AA PART NUMBER FOLLOWS THE PIECE (owner: "Mantener el mismo número"):
each variant keeps the AA Part # its old product carried - the engine moves it
like the barcode.
"""

from odoo import api, models

RAW_SURVIVOR = '%s" %s Track RAW'

LENGTH = "attribute_raw_track_length"
COLOUR = "attribute_finish_colour"
LINE = "attribute_hardware_line"


def raw_length_value(inches):
    """9'6", 7'4", or 15' for a whole number of feet."""
    feet, rest = divmod(int(inches), 12)
    return "%d'%d\"" % (feet, rest) if rest else "%d'" % feet


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _aa_raw_track_families(self):
        """The RAW track families this catalogue actually has, as merge specs."""
        templates = self.with_context(
            active_test=False, lang="en_US"
        ).search([("name", "ilike", "Track RAW")])

        found = {}

        for template in templates:
            # ACTIVE ONLY. An archived RAW product is either one this merge
            # already folded or one he retired by hand; neither is stock.
            if not template.active:
                continue

            variants = template.with_context(
                active_test=False).product_variant_ids

            # A template that already has choices is a merged RAW product.
            if len(variants) != 1:
                continue

            facts = variants._aa_raw_track_facts()
            if not facts:
                continue

            key = (facts["size"], facts["kind"])
            found.setdefault(key, {})[template.name] = {
                "facts": facts,
                "stock": variants.qty_available,
            }

        specs = [
            self._aa_raw_track_spec(size, kind, members)
            for (size, kind), members in sorted(found.items())
            if len(members) > 1
        ]

        # A FAMILY ALREADY FOLDED STILL GETS A LINE ON THE SCREEN. Once merged
        # there is no single-variant RAW product left to discover it from, so
        # without this the Catalogue Merge report would simply stop listing
        # it - which reads as "lost", not as "done".
        listed = {spec["survivor"] for spec in specs}
        attribute_ids = {
            xmlid: self.env.ref("spring_engineering.%s" % xmlid).id
            for xmlid in (LENGTH, COLOUR, LINE)
        }
        for template in templates.filtered("active"):
            if template.name in listed or len(template.product_variant_ids) < 2:
                continue
            for size in ("2", "3"):
                for kind in ("Horizontal", "Vertical"):
                    if template.name != RAW_SURVIVOR % (size, kind):
                        continue
                    have = set(template.attribute_line_ids.attribute_id.ids)
                    attributes = tuple(x for x, i in attribute_ids.items() if i in have)
                    if LENGTH in attributes:
                        specs.append({
                            "survivor": template.name, "base": None,
                            "attributes": attributes, "products": {},
                        })
                        listed.add(template.name)
        return specs

    @api.model
    def _aa_raw_track_spec(self, size, kind, members):
        """One RAW family, in the shape the merge engine reads."""
        with_line = any(m["facts"]["line"] == "atl" for m in members.values())

        products = {}
        for name, member in members.items():
            facts = member["facts"]
            combo = {
                LENGTH: raw_length_value(facts["inches"]),
                COLOUR: facts["colour"],
            }
            if with_line:
                combo[LINE] = facts["line"].upper()
            products[name] = combo

        # THE BASE IS THE BEST-STOCKED BLACK CHI ONE, the rule every family
        # follows - and never an ATL piece, whose template carries the 2x2
        # angle note that must stay on the ATL variants only.
        chi = {n: m for n, m in members.items() if m["facts"]["line"] == "chi"} or members
        blacks = [n for n, m in chi.items() if m["facts"]["colour"] == "Black"] or list(chi)
        base = max(sorted(blacks), key=lambda n: members[n]["stock"])

        lengths = [
            raw_length_value(inches)
            for inches in sorted({m["facts"]["inches"] for m in members.values()})
        ]

        attributes = (LENGTH, COLOUR) + ((LINE,) if with_line else ())
        order = {LENGTH: lengths}
        if with_line:
            order[LINE] = ["CHI", "ATL"]

        return {
            "survivor": RAW_SURVIVOR % (size, kind.title()),
            "base": base,
            "attributes": attributes,
            "products": products,
            "value_order": order,
        }
