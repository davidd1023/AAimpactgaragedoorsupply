"""FOLDING ONE PART'S COLOURS, SIZES AND HANDS INTO ONE PRODUCT.

The catalogue grew one supplier sheet at a time, so a bracket that comes in
two colours became two products and a hinge that comes in seven sizes became
twenty-one. The owner asked for one product per PART, with the colour, the
size and the hand chosen on its own page (2026-10-21). models/variant_families
says which old product becomes which variant of which product; this does it.

WHAT MAKES THIS DELICATE IS NOT THE ATTRIBUTES, IT IS EVERYTHING ELSE.
Adding an attribute to a template replaces its variants: Odoo archives the old
no-attribute variant and creates one per combination. The old record keeps the
stock, the reordering rules, the kit BoM lines that point at it and the setting
that names it. None of that follows by itself, so this does, in an order that
cannot lose a count:

  1. read every old product's stock, cost, part number, barcode and image;
  2. zero the stock OFF the old products, by inventory adjustment, so the
     numbers are moved rather than duplicated and the moves say why;
  3. build the attributes on the surviving product, which creates the variants;
  4. write each old product's part number, cost and image onto ITS variant and
     put its stock back, location by location;
  5. repoint everything that referenced the old variant - kit BoM lines,
     reordering rules, pricelist lines, supplier lines, draft quotations and
     purchase orders, and any setting that stores a product id;
  6. archive and unpublish what is left.

A FAMILY IS ALL OR NOTHING. Each one runs in its own savepoint, and anything
that does not add up - a product missing from the catalogue, a part number that
appears twice, two colours of one size that disagree about the price, stock
reserved on a delivery that has not gone out - skips that whole family and says
so. A half-merged family is the one outcome worse than an unmerged one: the
store would show a product whose variants are missing their stock.

NOTHING IS MATCHED BY POSITION. Every variant is found by attribute name and
value name (`_aa_variant_for`). Hand is why: this catalogue has exactly one
part with an LH and an RH, and a bracket of the wrong hand does not mount. The
old code that picks kit components took `variants[0]` when it could not tell
them apart, which is precisely the bug this must not reintroduce.

THE DRY RUN IS A REHEARSAL, NOT A GUESS. It performs the whole merge and rolls
it back, so the report says what did happen rather than what should. That is
the report to read on staging before this reaches Prod.
"""

import logging

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

from .variant_families import ATTRIBUTE_VALUES, FAMILIES

_logger = logging.getLogger(__name__)

# WHY THIS IS NOT IN garage_door_supply, where the catalogue otherwise lives:
# that module owns views/website_homepage.xml, which replaces the whole of the
# homepage's //div[@id='wrap'] and carries no noupdate. Every update of it puts
# the shipped hero back over whatever has been done in the website builder -
# the owner restored a backup on 2026-10-19 and watched the page change back.
# A merge needs a migration, a migration needs an update, and an update there
# costs him his front page. See aa_dealer_orders/__manifest__.py, which refuses
# to depend on that module for the same reason.
MODULE = "spring_engineering"

# A stock move that is neither done nor cancelled still has a claim on the
# quantity we are about to move to another product. Validating or cancelling it
# first is the owner's call, not ours.
MOVES_IN_THE_WAY = ("draft", "waiting", "confirmed", "partially_available", "assigned")

# Where an old variant id can be hiding, as (model, field). Every one of these
# is repointed at the new variant. Historical documents are deliberately NOT
# here: a done delivery or an invoiced order line says what was shipped and
# must go on saying it, pointing at the archived product.
REMAP_ALWAYS = (
    ("mrp.bom.line", "product_id"),
    ("mrp.bom", "product_id"),
    ("stock.warehouse.orderpoint", "product_id"),
    ("product.pricelist.item", "product_id"),
    ("stock.putaway.rule", "product_id"),
)

# Open paperwork, repointed so that confirming it does not ship an archived
# product with no stock on it. Anything further along is left alone.
#
# AND THE FIGURES ON IT ARE PUT BACK AFTERWARDS, which is the whole reason
# each entry carries a list of fields. Writing a product id on an order line
# recomputes its price from the pricelist: a quotation with 4.25 agreed on the
# phone came back out of an early version of this at 6.219. A price somebody
# has already been QUOTED must not move because we tidied the catalogue
# underneath it, and the description must go on saying what they were sent.
REMAP_IF_OPEN = (
    ("sale.order.line", "product_id", "order_id.state", ("draft", "sent"),
     ("name", "price_unit", "discount", "product_uom_qty", "tax_ids")),
    ("purchase.order.line", "product_id", "order_id.state", ("draft", "sent"),
     ("name", "price_unit", "discount", "product_qty", "taxes_id")),
)


class _FamilyRolledBack(Exception):
    """Raised to roll a rehearsal back once it has finished."""


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ------------------------------------------------------------------
    # the entry points
    # ------------------------------------------------------------------

    @api.model
    def _aa_merge_variant_families(self, dry_run=True, only=None):
        """Merge every family in variant_families. Returns a list of reports.

        `dry_run=True` rehearses and rolls back - that is the default, because
        the dangerous call should be the one you have to type out.
        """
        reports = []
        for spec in FAMILIES:
            if only and spec["survivor"] not in only:
                continue
            reports.append(self._aa_merge_one_family(spec, dry_run=dry_run))

        _logger.info(
            "AA variant merge (%s):\n%s",
            "rehearsal" if dry_run else "FOR REAL",
            self._aa_merge_report(reports),
        )
        return reports

    @api.model
    def _aa_merge_report(self, reports):
        """The reports as something a person can read down."""
        lines = []
        for r in reports:
            lines.append(
                "  %-28s %-12s %2d products -> %2d variants"
                % (r["survivor"], r["state"], r["products"], r["variants"])
            )
            for problem in r["problems"]:
                lines.append("        ! %s" % problem)
            for note in r["notes"]:
                lines.append("        - %s" % note)

        done = sum(1 for r in reports if r["state"] in ("merged", "rehearsed"))
        skipped = [r["survivor"] for r in reports if r["state"] == "skipped"]
        lines.append("  %d of %d families merged" % (done, len(reports)))
        if skipped:
            lines.append("  skipped: %s" % ", ".join(skipped))
        return "\n".join(lines)

    @api.model
    def _aa_merge_one_family(self, spec, dry_run=True):
        report = {
            "survivor": spec["survivor"],
            "state": "skipped",
            "products": len(spec["products"]),
            "variants": 0,
            "problems": [],
            "notes": [],
        }

        if self._aa_already_merged(spec):
            report["state"] = "already merged"
            return report

        olds, already = self._aa_family_products(spec, report)
        if already:
            report["state"] = "already merged"
            return report
        if report["problems"]:
            return report

        self._aa_check_family(spec, olds, report)
        if report["problems"]:
            return report

        try:
            with self.env.cr.savepoint():
                self._aa_do_merge(spec, olds, report)
                if dry_run:
                    raise _FamilyRolledBack()
        except _FamilyRolledBack:
            report["state"] = "rehearsed"
        except (UserError, ValueError) as exc:
            report["state"] = "skipped"
            report["problems"].append("merge failed, rolled back: %s" % exc)
        else:
            report["state"] = "merged"

        return report

    # ------------------------------------------------------------------
    # finding the family, and refusing to touch it if it does not add up
    # ------------------------------------------------------------------

    @api.model
    def _aa_already_merged(self, spec):
        """Has this family already been folded up?

        The question is asked of the SURVIVING product, not of the old ones:
        the base keeps its record and is renamed, so most of the old names are
        still in the database as archived products long after the merge. What
        says the work is done is a live product with the family's name carrying
        the family's choices.
        """
        survivor = self.env["product.template"].with_context(
            active_test=False, lang="en_US"
        ).search([("name", "=", spec["survivor"])])
        if not survivor:
            return False

        wanted = {
            self.env.ref("%s.%s" % (MODULE, attr)).id for attr in spec["attributes"]
        }
        for template in survivor:
            if wanted <= set(template.attribute_line_ids.attribute_id.ids):
                return True
        return False

    @api.model
    def _aa_family_products(self, spec, report):
        """{old name: template} for one family, or problems saying why not.

        Archived products count: a family half-merged by a previous crash must
        be recognised rather than merged again on top of itself.
        """
        Tmpl = self.env["product.template"].with_context(
            active_test=False, lang="en_US"
        )
        olds, missing = {}, []

        for name in spec["products"]:
            found = Tmpl.search([("name", "=", name)])
            if len(found) == 1:
                olds[name] = found
            elif not found:
                missing.append(name)
            else:
                report["problems"].append(
                    "%r matches %d products, so it is not clear which to merge"
                    % (name, len(found))
                )

        survivor = Tmpl.search([("name", "=", spec["survivor"])])
        if missing and len(missing) == len(spec["products"]) and survivor:
            # Every old name gone and the merged product there: this ran before.
            return olds, True

        if missing:
            report["problems"].append(
                "%d of %d products not in the catalogue: %s"
                % (len(missing), len(spec["products"]), ", ".join(sorted(missing)))
            )

        return olds, False

    @api.model
    def _aa_check_family(self, spec, olds, report):
        """Everything that must be true before a single row is written."""
        if not olds:
            return

        # ONE VARIANT EACH. These are plain products today; one that already
        # has attributes has been touched by hand and is not ours to fold.
        for name, tmpl in olds.items():
            count = len(tmpl.with_context(active_test=False).product_variant_ids)
            if count != 1:
                report["problems"].append(
                    "%r already has %d variants" % (name, count)
                )

        # THE SAME KIND OF THING THROUGHOUT. A different unit or a different
        # tax is not a variant of a product, it is a different product, and
        # folding them would quietly reprice or re-measure one of them.
        for field, label in (
            ("uom_id", "unit"),
            ("type", "type"),
            ("taxes_id", "customer taxes"),
            ("supplier_taxes_id", "vendor taxes"),
        ):
            seen = {tuple(sorted(t[field].ids)) if t._fields[field].type
                    in ("many2many", "one2many") else t[field]
                    for t in olds.values()}
            if len(seen) > 1:
                report["problems"].append(
                    "the %s is not the same across the family" % label
                )

        # PART NUMBERS MUST NOT COLLIDE. Two products sharing one reference is
        # normal here and fine - they become two variants - but the same
        # reference on two DIFFERENT combinations of the same family would make
        # the merged product ambiguous to anything that looks a part up by SKU.
        codes = {}
        for name, tmpl in olds.items():
            code = tmpl.default_code
            if code:
                codes.setdefault(code, []).append(name)
        for code, names in codes.items():
            combos = {tuple(sorted(spec["products"][n].items())) for n in names}
            if len(combos) != len(names):
                report["notes"].append(
                    "part number %s is on %d of these products" % (code, len(names))
                )

        # NOT LOT OR SERIAL TRACKED. The stock is moved by recreating its
        # quants on the new variant, and a quant carries its lot - but a lot
        # belongs to ONE product, so the old product's lot numbers cannot
        # follow it. None of these families is tracked today; if one ever is,
        # this says so rather than inventing lot numbers.
        tracked = sorted(
            name for name, tmpl in olds.items() if tmpl.tracking != "none"
        )
        if tracked:
            report["problems"].append(
                "lot or serial tracked, so the stock cannot be moved by hand:"
                " %s" % ", ".join(tracked)
            )

        # NOTHING RESERVED OR IN FLIGHT. We are about to move the stock to
        # another product; a picking that has not gone out has a claim on it.
        variants = self.env["product.product"].with_context(active_test=False).browse(
            [t.product_variant_ids[:1].id for t in olds.values() if t.product_variant_ids]
        )
        moves = self.env["stock.move"].search(
            [("product_id", "in", variants.ids), ("state", "in", MOVES_IN_THE_WAY)]
        )
        if moves:
            where = ", ".join(sorted({m.reference or "?" for m in moves})[:6])
            report["problems"].append(
                "%d stock moves are still open on these products (%s) - validate"
                " or cancel them first" % (len(moves), where)
            )

        # THE PRICE HAS TO BE EXPLAINABLE BY THE CHOICES. A variant's price is
        # the product's price plus an extra per chosen value, so the old prices
        # must be additive. They are, in this catalogue: colour never moves a
        # price and size always does. If that ever stops being true, this says
        # so instead of repricing the family.
        self._aa_price_plan(spec, olds, report)

        # A SIBLING NOBODY TOLD US ABOUT. If a colour was added to the
        # catalogue after the export this table was built from, it would be
        # left behind as an orphan product. Advisory only - it does not stop
        # the merge, it just must not pass unnoticed.
        self._aa_note_unmapped_siblings(spec, olds, report)

    @api.model
    def _aa_price_plan(self, spec, olds, report):
        """{(attribute xmlid, value): extra} and the product's own price.

        None if the old prices cannot be expressed that way.
        """
        base_combo = spec["products"][spec["base"]]
        price_of = {
            tuple(sorted(spec["products"][name].items())): tmpl.list_price
            for name, tmpl in olds.items()
        }
        base_key = tuple(sorted(base_combo.items()))
        if base_key not in price_of:
            return None

        base_price = price_of[base_key]
        extras = {}
        for attr in spec["attributes"]:
            for value in self._aa_family_values(spec, attr):
                if value == base_combo[attr]:
                    extras[(attr, value)] = 0.0
                    continue
                probe = dict(base_combo, **{attr: value})
                found = price_of.get(tuple(sorted(probe.items())))
                if found is None:
                    report["problems"].append(
                        "cannot price %s=%s: that combination is not in the"
                        " catalogue" % (attr, value)
                    )
                    return None
                extras[(attr, value)] = found - base_price

        # And now the test: does every old price fall out of those extras?
        rounding = self.env.company.currency_id.rounding
        for name, combo in spec["products"].items():
            if name not in olds:
                continue
            want = olds[name].list_price
            got = base_price + sum(extras[(a, v)] for a, v in combo.items())
            if float_compare(want, got, precision_rounding=rounding):
                report["problems"].append(
                    "%r is priced %s but its choices add up to %s - the family"
                    " cannot be priced by attribute" % (name, want, got)
                )
                return None

        return {"base_price": base_price, "extras": extras}

    @api.model
    def _aa_family_values(self, spec, attr):
        """The values one family uses for one attribute, in page order."""
        used = {combo[attr] for combo in spec["products"].values()}
        return [v for v in ATTRIBUTE_VALUES[attr] if v in used]

    @api.model
    def _aa_note_unmapped_siblings(self, spec, olds, report):
        names = list(spec["products"])
        prefix = ""
        for i, char in enumerate(names[0]):
            if all(len(n) > i and n[i] == char for n in names):
                prefix += char
            else:
                break
        if len(prefix) < 6:
            return  # too vague to search on without dragging the catalogue in

        siblings = self.env["product.template"].with_context(
            active_test=False, lang="en_US"
        ).search([("name", "=like", prefix + "%")])
        strays = [s.name for s in siblings if s.name not in spec["products"]]
        if strays:
            report["notes"].append(
                "not in the table, left alone: %s" % ", ".join(sorted(strays))
            )

    # ------------------------------------------------------------------
    # the merge itself
    # ------------------------------------------------------------------

    @api.model
    def _aa_do_merge(self, spec, olds, report):
        plan = self._aa_price_plan(spec, olds, report)
        if not plan:
            raise UserError("the family cannot be priced by attribute")

        snapshot = self._aa_snapshot(olds)
        self._aa_zero_stock(snapshot)

        base = olds[spec["base"]]
        self._aa_build_attributes(spec, base, plan)

        base.invalidate_recordset()
        # active_test=True SAID OUT LOUD: the family was looked up with
        # archived products included, and that context would otherwise count
        # the base's own replaced variant as one of the new ones.
        report["variants"] = len(
            base.with_context(active_test=True).product_variant_ids
        )

        for name, combo in spec["products"].items():
            if name not in olds:
                continue
            target = self._aa_variant_for(base, combo)
            if not target:
                raise UserError("no variant for %r (%s)" % (name, combo))
            self._aa_restore(snapshot[name], target, report)

        self._aa_check_prices(spec, olds, base, report)
        self._aa_retire(spec, olds, base, report)

    @api.model
    def _aa_snapshot(self, olds):
        """Everything about the old products that has to survive them."""
        snapshot = {}
        for name, tmpl in olds.items():
            variant = tmpl.with_context(active_test=False).product_variant_ids[:1]
            quants = self.env["stock.quant"].search([
                ("product_id", "=", variant.id),
                ("location_id.usage", "in", ("internal", "transit")),
            ])
            snapshot[name] = {
                "template": tmpl,
                "variant": variant,
                "default_code": variant.default_code or tmpl.default_code,
                "barcode": variant.barcode,
                "standard_price": variant.standard_price,
                "weight": variant.weight,
                "volume": variant.volume,
                "image": variant.image_1920 or tmpl.image_1920,
                "published": tmpl.is_published,
                "quants": [
                    {
                        "location_id": q.location_id.id,
                        "lot_id": q.lot_id.id,
                        "owner_id": q.owner_id.id,
                        "package_id": q.package_id.id,
                        "quantity": q.quantity,
                    }
                    for q in quants
                    if not float_is_zero(q.quantity, precision_rounding=0.001)
                ],
            }
        return snapshot

    @api.model
    def _aa_zero_stock(self, snapshot):
        """Take the stock off the old products, by inventory adjustment.

        AN ADJUSTMENT RATHER THAN A WRITE, so the count leaves a move behind
        saying where it went, and so valuation follows. It happens before the
        attributes are built because Odoo will not let a variant with stock be
        replaced cleanly, and because stock that exists on both the old product
        and the new one for even one statement is stock counted twice.
        """
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        for entry in snapshot.values():
            if not entry["quants"]:
                continue
            quants = Quant.search([
                ("product_id", "=", entry["variant"].id),
                ("location_id.usage", "in", ("internal", "transit")),
            ])
            if quants:
                quants.write({"inventory_quantity": 0})
                quants.action_apply_inventory()

    @api.model
    def _aa_build_attributes(self, spec, base, plan):
        """Turn the surviving product into the family, with its variants."""
        lines = []
        for attr_xmlid in spec["attributes"]:
            attribute = self.env.ref("%s.%s" % (MODULE, attr_xmlid))
            values = self._aa_values_for(
                attribute, attr_xmlid, self._aa_family_values(spec, attr_xmlid)
            )
            lines.append({
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, values.ids)],
            })

        base.write({
            "name": spec["survivor"],
            "list_price": plan["base_price"],
            "attribute_line_ids": [(0, 0, line) for line in lines],
        })

        # THE EXTRAS GO ON AFTER THE LINES EXIST, because the records that
        # carry a price extra (product.template.attribute.value) are created by
        # writing the lines above.
        for (attr_xmlid, value_name), extra in plan["extras"].items():
            if float_is_zero(extra, precision_rounding=0.0001):
                continue
            attribute = self.env.ref("%s.%s" % (MODULE, attr_xmlid))
            ptav = base.attribute_line_ids.filtered(
                lambda l, a=attribute: l.attribute_id == a
            ).product_template_value_ids.filtered(
                lambda v, n=value_name: v.name == n
            )
            ptav.price_extra = extra

    @api.model
    def _aa_values_for(self, attribute, attr_xmlid, names):
        """The attribute values for these names, created if they are new.

        The sequence follows ATTRIBUTE_VALUES, so "#10" comes before "#16" and
        8'6" before 10'6" - orders no sort would give us.
        """
        found = self.env["product.attribute.value"]
        order = {
            name: position
            for position, name in enumerate(ATTRIBUTE_VALUES[attr_xmlid])
        }
        for name in names:
            value = self.env["product.attribute.value"].search([
                ("attribute_id", "=", attribute.id),
                ("name", "=", name),
            ], limit=1)
            if not value:
                value = self.env["product.attribute.value"].create({
                    "attribute_id": attribute.id,
                    "name": name,
                    "sequence": order[name],
                })
            found |= value
        return found

    @api.model
    def _aa_variant_for(self, template, combo):
        """The variant of `template` matching {attribute xmlid: value name}.

        BY NAME, NEVER BY POSITION - see the module docstring. This is the one
        function a wrong-hand bracket would come through.
        """
        want = {}
        for attr_xmlid, value_name in combo.items():
            want[self.env.ref("%s.%s" % (MODULE, attr_xmlid)).id] = value_name

        for variant in template.with_context(active_test=False).product_variant_ids:
            got = {
                ptav.attribute_id.id: ptav.name
                for ptav in variant.product_template_attribute_value_ids
            }
            if got == want:
                return variant
        return self.env["product.product"]

    @api.model
    def _aa_restore(self, entry, target, report):
        """Put one old product's identity and stock onto its new variant."""
        values = {
            "default_code": entry["default_code"],
            "standard_price": entry["standard_price"],
        }
        if entry["barcode"]:
            values["barcode"] = entry["barcode"]
        if entry["weight"]:
            values["weight"] = entry["weight"]
        if entry["volume"]:
            values["volume"] = entry["volume"]
        # The variant's own photo, so a white bracket can look white. The old
        # products each had their own picture and there is nowhere else for it
        # to go: a template carries one image, a variant carries its own.
        if entry["image"]:
            values["image_variant_1920"] = entry["image"]
        target.write(values)

        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        for quant in entry["quants"]:
            new = Quant.create({
                "product_id": target.id,
                "location_id": quant["location_id"],
                "lot_id": quant["lot_id"],
                "owner_id": quant["owner_id"],
                "package_id": quant["package_id"],
                "inventory_quantity": quant["quantity"],
            })
            new.action_apply_inventory()

        self._aa_move_vendor_lines(entry, target, report)
        self._aa_repoint(entry["variant"], target, report)

    @api.model
    def _aa_move_vendor_lines(self, entry, target, report):
        """The vendor prices for one old product, onto its new variant.

        WHY THIS IS NOT IN THE REMAP TABLE. A vendor line usually hangs off the
        TEMPLATE with no variant at all (product_tmpl_id set, product_id
        false), which is how Odoo stores "this is what this part costs from
        this supplier". Repointing by variant id would miss every one of them,
        and the lines would be stranded on an archived template: the reordering
        rules would still fire and there would be no vendor price to buy at.

        So each old product's lines become VARIANT-SPECIFIC on the surviving
        product. That includes the base's own, which would otherwise be the one
        template-level line left applying to every colour - a white bracket
        quietly bought at the black one's price.
        """
        Supplier = self.env["product.supplierinfo"]
        lines = Supplier.search([
            "|",
            ("product_id", "=", entry["variant"].id),
            "&", ("product_tmpl_id", "=", entry["template"].id),
            ("product_id", "=", False),
        ])
        for line in lines:
            if line.product_tmpl_id == target.product_tmpl_id:
                # The base's own line: it is already on the right template, it
                # just has to stop speaking for all the other colours.
                line.product_id = target.id
            else:
                line.copy({
                    "product_tmpl_id": target.product_tmpl_id.id,
                    "product_id": target.id,
                })
        if lines:
            report["notes"].append(
                "%s: %d vendor price line(s) moved onto the variant"
                % (entry["variant"].display_name, len(lines))
            )

    @api.model
    def _aa_repoint(self, old, new, report):
        """Everything that pointed at the old variant now points at the new."""
        moved = {}

        for model, field in REMAP_ALWAYS:
            if model not in self.env:
                continue
            records = self.env[model].with_context(active_test=False).search(
                [(field, "=", old.id)]
            )
            if records:
                records.write({field: new.id})
                moved[model] = moved.get(model, 0) + len(records)

        for model, field, state_field, states, preserve in REMAP_IF_OPEN:
            if model not in self.env:
                continue
            records = self.env[model].search(
                [(field, "=", old.id), (state_field, "in", states)]
            )
            for record in records:
                # Read the figures, repoint, write the figures back. The second
                # write is what beats the recompute the first one triggers.
                kept = {
                    name: record[name]
                    for name in preserve
                    if name in record._fields
                }
                record.write({field: new.id})
                record.write({
                    name: (value.ids if hasattr(value, "ids") else value)
                    for name, value in kept.items()
                })
            if records:
                moved[model] = moved.get(model, 0) + len(records)

        # A SETTING THAT NAMES A PRODUCT. The flag angle for prepared tracks is
        # stored as a product id in a config parameter, and a prepared track
        # whose flag angle had been archived would silently lose it.
        params = self.env["ir.config_parameter"].sudo().search(
            [("key", "=like", "%_product_id")]
        )
        for param in params:
            if (param.value or "").strip() == str(old.id):
                param.value = str(new.id)
                moved["ir.config_parameter"] = moved.get("ir.config_parameter", 0) + 1

        if moved:
            report["notes"].append(
                "%s: repointed %s"
                % (old.display_name,
                   ", ".join("%d %s" % (n, m) for m, n in sorted(moved.items())))
            )

        # WHAT IS LEFT POINTING AT THE ARCHIVED PRODUCT, said out loud. Done
        # deliveries and invoiced lines are meant to stay where they are; this
        # is here so the number is a decision and not a surprise.
        history = self.env["stock.move"].search_count([("product_id", "=", old.id)])
        if history:
            report["notes"].append(
                "%s: %d historical stock moves left on the archived product"
                % (old.display_name, history)
            )

    @api.model
    def _aa_check_prices(self, spec, olds, base, report):
        """Every new variant must cost what its old product cost."""
        rounding = self.env.company.currency_id.rounding
        for name, combo in spec["products"].items():
            if name not in olds:
                continue
            target = self._aa_variant_for(base, combo)
            want = olds[name].list_price
            if float_compare(target.lst_price, want, precision_rounding=rounding):
                raise UserError(
                    "%r priced %s, its variant prices %s"
                    % (name, want, target.lst_price)
                )

    @api.model
    def _aa_retire(self, spec, olds, base, report):
        """Archive and unpublish the products that were folded in."""
        published = any(
            tmpl.is_published for tmpl in olds.values()
        )
        base.is_published = published

        # THE SHOP CATEGORIES OF ALL OF THEM, not just the base's. The base is
        # chosen for its stock, and if a sibling sat in a category it did not,
        # the merged product would quietly drop out of that part of the shop.
        categories = base.public_categ_ids
        for tmpl in olds.values():
            categories |= tmpl.public_categ_ids
        if categories != base.public_categ_ids:
            base.public_categ_ids = [(6, 0, categories.ids)]
            report["notes"].append(
                "shop categories: %s" % ", ".join(sorted(categories.mapped("name")))
            )

        for name, tmpl in olds.items():
            if tmpl == base:
                continue
            tmpl.write({"is_published": False, "active": False})


class ProductProduct(models.Model):
    _inherit = "product.product"

    # The spellings a finish attribute answers to. The catalogue was not built
    # on one day and aa_dealer_orders already reads all four
    # (custom_kit.py COLOUR_ATTRIBUTES); this is the same list, so a product
    # the owner set up by hand as "Color" is understood too.
    AA_COLOUR_ATTRIBUTES = ("colour", "color", "finish colour", "finish color")

    def _aa_choice_text(self):
        """This product's name with the values it was chosen in.

        THE POINT OF THIS FUNCTION. Half the shop used to read a colour or a
        size out of a product NAME, because that is where they were: "Jamb
        Bracket # 10 Black" said its size and its finish out loud. After the
        merge the name is "Jamb Bracket" and the size and the finish are
        variant values, so every one of those readers would come up empty -
        and a bracket that is not found takes the whole prepared track with it
        (_track_prep_sync adds every part or none).

        So the readers go on reading a name; this is just a longer name. Before
        the merge it returns the name unchanged, which is why the same code
        works on a database that has not been merged yet - and on the owner's,
        between the deploy and the migration.
        """
        self.ensure_one()
        chosen = self.product_template_attribute_value_ids.mapped("name")
        return " ".join([self.name or ""] + [v for v in chosen if v])

    def _aa_chosen_colour(self):
        """The finish this variant was chosen in, or "" if it has no finish."""
        self.ensure_one()
        for ptav in self.product_template_attribute_value_ids:
            if (ptav.attribute_id.name or "").strip().lower() in self.AA_COLOUR_ATTRIBUTES:
                return (ptav.name or "").strip()
        return ""

    def _aa_pick_stable(self):
        """One of several candidates - THE SAME ONE EVERY TIME.

        A tolerant lookup that matched one product could be left matching
        several once its colour stopped being part of its name: "Flag Angle
        Black" used to name one product and now describes a Black flag angle
        in either of two sizes. Ordering by name no longer separates them -
        every variant of a product shares its name - so a plain `limit=1`
        would hand out whichever the database happened to return first, and a
        different one on the next order.

        The order here is the page order: the sequence of the chosen values,
        then the id. For the flag angles that means 5.9" before 6-3/8", which
        is what the old alphabetical-by-name lookup was giving the owner by
        accident. Preserving an accident is deliberate - it is still what his
        orders have been getting - and it is the setting
        (spring_engineering.track_prep_flag_product_id) that overrides it until
        he says which size a prepared track should take.
        """
        return self.sorted(
            key=lambda p: (
                [v.product_attribute_value_id.sequence
                 for v in p.product_template_attribute_value_ids],
                p.id,
            )
        )[:1]
