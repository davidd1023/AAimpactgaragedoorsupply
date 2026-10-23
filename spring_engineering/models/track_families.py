"""THE TRACK FAMILIES, READ OFF THE CATALOGUE RATHER THAN LISTED.

Every other family in variant_families.py is a hand-checked table of product
names, generated from the owner's export. The tracks are not, and deliberately:

  * their names are irregular in a way a table cannot survive. "2" Horizontal
    Track -  120" White" has two spaces after the dash and "- 108" Black" has
    one, inconsistently, row by row. One transcription slip and that family is
    skipped;
  * there are four families and about thirty-two products, and the facts that
    sort them - size, type, length, finish - are already read by a tested
    reader (product.product._aa_track_facts), written for exactly these names;
  * he adds lengths. A table would go stale the first time a 144" horizontal
    arrives; this finds it.

So the four families - 2" and 3", horizontal and vertical (owner, 2026-10-23:
"they should be separated by 3" and 2", and also track type so horizontal and
vertical") - are assembled from whatever the catalogue actually holds, in the
same shape the table produces, and handed to the same engine. The rehearsal
screen then shows them beside the others, with the same refusals.

RAW STOCK IS NOT HERE. It is what a track is cut FROM and the owner kept it
out (2026-10-23: "Leave RAW alone, merge only the cut tracks"). _aa_track_facts
refuses it outright, so it cannot be swept in by accident.
"""

from odoo import api, models

SURVIVOR = '%s" %s Track'


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _aa_track_length_value(self, facts):
        """What this track's length is called on the page.

        A VERTICAL TRACK KEEPS ITS DOOR HEIGHT. The catalogue has always said
        "76" - 7' Door Height", the shop floor reads the height back out of
        it, and a customer picks a track by the door it is for rather than by
        a number of inches. A horizontal track is just its length.
        """
        inches = "%g\"" % facts["length"]

        if facts["kind"] == "vertical" and facts["door"]:
            return "%s - %d' Door Height" % (inches, facts["door"])

        return inches

    @api.model
    def _aa_track_families(self):
        """The track families this catalogue actually has, as merge specs."""
        templates = self.with_context(
            active_test=False, lang="en_US"
        ).search([("name", "ilike", "Track")])

        found = {}

        for template in templates:
            variants = template.with_context(
                active_test=False).product_variant_ids

            # A TEMPLATE THAT ALREADY HAS CHOICES ON IT is either a merged
            # track or something else entirely; either way it is not one of
            # the products being folded in.
            if len(variants) != 1:
                continue

            facts = variants._aa_track_facts()

            if not facts:
                continue

            key = (facts["size"], facts["kind"])
            found.setdefault(key, {})[template.name] = {
                "facts": facts,
                "stock": variants.qty_available,
            }

        return [
            self._aa_track_spec(size, kind, members)
            for (size, kind), members in sorted(found.items())
        ]

    @api.model
    def _aa_track_spec(self, size, kind, members):
        """One family, in the shape the merge engine reads."""
        products = {
            name: {
                "attribute_track_length": self._aa_track_length_value(
                    member["facts"]),
                "attribute_finish_colour": member["facts"]["colour"],
            }
            for name, member in members.items()
        }

        # THE BASE IS THE BEST-STOCKED BLACK ONE, the same rule the table
        # uses: the row most likely to be the one people have been buying,
        # and so the one whose record is worth keeping.
        blacks = [name for name, member in members.items()
                  if member["facts"]["colour"] == "Black"] or list(members)
        base = max(sorted(blacks), key=lambda name: members[name]["stock"])

        # SHORTEST FIRST, by the inches themselves rather than by the text:
        # "108"" sorts before "96"" as a string, which is not how anybody
        # reads a list of lengths.
        lengths = sorted(
            {self._aa_track_length_value(m["facts"]) for m in members.values()},
            key=lambda value: float(value.split('"')[0]),
        )

        return {
            "survivor": SURVIVOR % (size, kind.title()),
            "base": base,
            "attributes": ("attribute_track_length", "attribute_finish_colour"),
            "products": products,
            # Discovered values have no place in ATTRIBUTE_VALUES, so the
            # family carries its own order.
            "value_order": {"attribute_track_length": lengths},
        }
