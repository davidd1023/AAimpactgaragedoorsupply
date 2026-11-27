"""LIFT CABLES CUT, DEDUCTED AND CHARGED BY THE AA CALCULATOR (owner, 2026-11-27).

"haz ese cambio para que se calcule, se descuente y se cobren por esa formula"
- after seeing that the prepared cable pairs carried one fixed length per
whole-foot door (a 98" door got the 9' pair, 129" a cable, where the
calculator says 119").

A prepared pair is still the product on the order - it says the cable size,
the radius and roughly the door - but the LENGTH each cable is cut to is now
the AA calculator's, worked out from the door the cable belongs to:

  * `sale.order.line._aa_cable_cut_calc()` - inches per cable, or 0 when the
    door does not say enough (then everything falls back to the pair's own
    recipe, exactly as before);
  * PRICE: the pair's price scaled by what the cable costs at that length
    against what it costs at the recipe's length (reel feet at the reel's
    cost, sleeves, thimbles and stops unchanged) - same margin, real length;
  * STOCK: when the delivery explodes the pair into its parts, the reel is
    taken at 2 x the cut per pair instead of the recipe's feet;
  * SHOP FLOOR and STICKER: the Cut row and the box sticker print the same
    figure (`_aa_cable_cut_inches(product, line)`).

High lift and LHR doors still have no prepared pair to put on the order
(door_options.py notes "AA cuts it"); that is unchanged.
"""

import re

from odoo import api, models

from .box_sticker import aa_calculator_ftsc_cable
from .sale_order import is_prepared_cable

CABLE_TRACK = re.compile(r'(\d)"\s*Track\s*\((\d+)R\)', re.I)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _aa_cable_door_line(self):
        """The hardware kit line this cable pair belongs to, or an empty set:
        the kit it is linked to, else the closest kit above it on the order."""
        self.ensure_one()
        def is_kit(line):
            return "Hardware Kit" in (line.product_id.product_tmpl_id.name or "")
        if self.linked_line_id and is_kit(self.linked_line_id):
            return self.linked_line_id
        lines = self.order_id.order_line.sorted(lambda l: (l.sequence, l.id))
        kit = self.env["sale.order.line"]
        first = kit
        for line in lines:
            if line == self:
                return kit or first
            if is_kit(line):
                kit = line
                first = first or line
        return kit

    def _aa_cable_cut_calc(self):
        """Inches each cable of this prepared pair is cut to, by the AA
        calculator, or 0.0 when the door does not say enough."""
        self.ensure_one()
        if not is_prepared_cable(self.product_id):
            return 0.0
        kit = self._aa_cable_door_line()
        if not kit or not kit.aa_door_height_in:
            return 0.0
        fields_ = kit._fields
        track = kit.aa_track_type if "aa_track_type" in fields_ else False
        if not track:
            hit = CABLE_TRACK.search(self.product_id.display_name or "")
            track = "%s-%sR" % (hit.group(1), hit.group(2)) if hit else False
        lift = (kit.aa_lift_type if "aa_lift_type" in fields_ else False) or "standard"
        high = (kit.aa_high_lift if "aa_high_lift" in fields_ else 0.0) or 0.0
        drum = kit.aa_drum if "aa_drum" in fields_ else False
        if not drum:
            drum = kit.product_id.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_id.name == "Drum")[:1].name or False
        _ftsc, cable = aa_calculator_ftsc_cable(kit.aa_door_height_in, track, lift, high, drum)
        return float(cable or 0.0)

    # --- the pair's recipe --------------------------------------------------

    def _aa_cable_recipe(self):
        """(phantom BoM, reel BoM line) of this pair, or (None, None)."""
        bom = self.env["mrp.bom"].sudo()._bom_find(self.product_id, bom_type="phantom").get(self.product_id)
        reel = bom and bom.bom_line_ids.filtered(lambda l: "reel" in (l.product_id.name or "").lower())[:1]
        return (bom, reel) if reel else (None, None)

    @staticmethod
    def _aa_reel_qty_for(reel_line, cut_in, pairs=1.0):
        """Reel quantity, in the BoM line's own unit, for `pairs` pairs cut to `cut_in`."""
        uom = (reel_line.product_uom_id.name or "").lower()
        inches = 2.0 * cut_in * pairs
        return inches if uom in ("in", "inch", "inches") else inches / 12.0

    def _aa_cable_price_ratio(self, cut_in):
        bom, reel = self._aa_cable_recipe()
        if not bom:
            return 1.0
        per = bom.product_qty or 1.0
        new_reel = self._aa_reel_qty_for(reel, cut_in) * per
        def cost(reel_qty):
            total = 0.0
            for line in bom.bom_line_ids:
                qty = reel_qty if line == reel else line.product_qty
                qty = line.product_uom_id._compute_quantity(qty, line.product_id.uom_id, round=False)
                total += qty * line.product_id.standard_price
            return total
        old_cost, new_cost = cost(reel.product_qty), cost(new_reel)
        if old_cost > 0 and new_cost > 0:
            return new_cost / old_cost
        return new_reel / reel.product_qty if reel.product_qty else 1.0

    def _get_pricelist_price(self):
        price = super()._get_pricelist_price()
        if is_prepared_cable(self.product_id):
            cut = self._aa_cable_cut_calc()
            if cut:
                price *= self._aa_cable_price_ratio(cut)
        return price


class StockRule(models.Model):
    _inherit = "stock.rule"

    @api.model
    def run(self, procurements, raise_user_error=True):
        """A prepared pair goes out as its parts; the reel is taken at the
        calculator's cut, not the recipe's feet. Everything else untouched."""
        kept, exploded = [], []
        for procurement in procurements:
            line_id = procurement.values.get("sale_line_id")
            line = self.env["sale.order.line"].browse(line_id) if line_id else None
            cut = line._aa_cable_cut_calc() if line and line.exists() else 0.0
            bom, reel = (line._aa_cable_recipe() if cut else (None, None))
            if not bom or bom.product_id and bom.product_id != procurement.product_id \
                    or procurement.product_id != line.product_id:
                kept.append(procurement)
                continue
            order_qty = procurement.product_uom._compute_quantity(
                procurement.product_qty, bom.product_uom_id, round=False)
            pairs = order_qty / (bom.product_qty or 1.0)
            _boms, sub_lines = bom.explode(procurement.product_id, pairs)
            for bom_line, data in sub_lines:
                qty = data["qty"]
                if bom_line == reel:
                    qty = self.env["sale.order.line"]._aa_reel_qty_for(reel, cut, pairs)
                values = dict(procurement.values, bom_line_id=bom_line.id)
                component_qty, uom = bom_line.product_uom_id._adjust_uom_quantities(qty, bom_line.product_id.uom_id)
                exploded.append(self.env["stock.rule"].Procurement(
                    bom_line.product_id, component_qty, uom, procurement.location_id,
                    procurement.name, procurement.origin, procurement.company_id, values))
        return super().run(kept + exploded, raise_user_error=raise_user_error)
