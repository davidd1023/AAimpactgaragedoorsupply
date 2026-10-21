import json
import logging

from odoo import fields, models

from ..pricing import CONE_PRICES, FILLER_PRICE_PER_FOOT, STEEL_COST_PER_LB

_logger = logging.getLogger(__name__)

# THE LIVE COST OF STEEL. pricing.py holds the default; this is the row the
# owner edits in Website > Configuration > Settings, read fresh every time so a
# change takes effect without a restart - the same arrangement as the sell rate.
STEEL_COST_KEY = "spring_engineering.steel_cost_per_lb"

# The calculator's own two products. Their price is written onto the LINE, not
# held on the product, so their cost has to be worked out the same way.
SPRING_REF = "spring_engineering.product_custom_spring"
FILLER_REF = "spring_engineering.product_custom_filler"


class SaleOrder(models.Model):
    """WHAT THE CART COSTS US, shown to staff and to nobody else.

    A member of staff looking at a cart - their own, or one they are building
    for a customer on the phone - is asked a question the page cannot answer:
    is this order worth taking? The sale price is on the screen; the cost is
    on each product's form, one product at a time, which is no use while the
    cart is in front of you.

    So the cart adds up what is in it and prints the figure under the Total.
    For a catalogue product that is the number the product form calls Cost
    (`standard_price`) - nothing inferred and no margin applied, because a
    figure arrived at by a calculation of ours would be a different claim from
    the one the product form makes.

    THE CALCULATOR'S OWN PRODUCTS HAVE NO SUCH FIELD TO READ, and are not
    meant to: a custom spring is a different thing every time it is ordered,
    which is why its price is written onto the line rather than held on a
    product. Those lines are costed the way they were priced - the same
    weights, off the same stored specification, with the COST of steel in
    place of its selling price. The two figures are then built the same way
    and can be read side by side.
    """

    _inherit = "sale.order"

    def _aa_cart_cost(self):
        """The cart's production cost, or None for anyone not on the staff.

        Returns ``{"cost": float, "unpriced": int}``:

          * ``cost`` - the sum of Cost x quantity, in the ORDER's currency.
          * ``unpriced`` - how many lines carry no cost at all, so the page
            can say so. A product whose Cost is blank contributes nothing,
            and a total that is quietly short is worse than no total: it
            reads like a real cost and it is not one. A catalogue product
            nobody has costed is the usual case; a custom spring joins it
            only when the steel cost has not been set or the line carries no
            specification to work from.

        NONE, NOT ZERO, FOR A CUSTOMER. The check is here rather than in the
        template on purpose: the template is editable from the website editor
        and this is not a figure to leave one xpath away from a shopper.
        """
        self.ensure_one()

        if not self.env.user._is_internal():
            return None

        # THE COMPANY'S OWN MONEY, AND THE COMPANY'S OWN BOOKS. `standard_price`
        # is company-dependent, so it is read for the company the order belongs
        # to rather than for whichever company the reader happens to be in.
        company = self.company_id or self.env.company
        cost = 0.0
        unpriced = 0

        # Read once for the whole cart rather than per line: it is one row in
        # ir_config_parameter and a cart can hold several assemblies.
        steel_cost = self._aa_steel_cost_per_lb()
        configured = self._door_configured_price_products()

        for line in self.order_line:
            # Sections, notes and the shipping line are not goods. Delivery in
            # particular has no cost of its own to speak of, and counting it as
            # a product with a blank cost would raise a warning about a line
            # that was never going to have one.
            if line.display_type or line.is_delivery or not line.product_id:
                continue

            # THE CALCULATOR'S OWN PRODUCTS HAVE NO COST FIELD TO READ, and are
            # not meant to: a custom spring is a different thing every time it
            # is ordered, so what it costs is worked out from the specification
            # on the line, the same way its price was. Taken first, because the
            # Cost field below says zero for both of them and always will.
            if line.product_id in configured:
                worked_out = self._aa_configured_line_cost(line, steel_cost)

                if worked_out is None:
                    if line.product_uom_qty:
                        unpriced += 1
                else:
                    cost += worked_out

                continue

            # EVERY LINE, including the fasteners folded under a bracket. They
            # are hidden from the cart as rows of their own, not from the
            # order: they are picked, shipped and paid for, so they cost.
            product = line.product_id.sudo().with_company(company)
            qty = line.product_uom_qty

            # Cost is per the product's OWN unit. A line sold by the dozen
            # against a cost held per piece is a twelvefold error, and the one
            # place it shows up here is the lift cable reel, bought by the foot.
            if (
                line.product_uom_id
                and product.uom_id
                and line.product_uom_id != product.uom_id
            ):
                qty = line.product_uom_id._compute_quantity(qty, product.uom_id)

            unit = product.standard_price or 0.0

            if not unit:
                # A HEADER IS NOT AN UNCOSTED PRODUCT. A custom kit's own line
                # lists at nothing on purpose - the parts carry the money, each
                # on its own line - so its cost is the cost of those lines and
                # has already been counted by the time we reach them. Warning
                # about it would send somebody looking for a Cost field that is
                # meant to be empty.
                if line.linked_line_ids and not line.price_unit:
                    continue

                # A zero-quantity line is nothing to warn about.
                if qty:
                    unpriced += 1
                continue

            cost += unit * qty

        # The cost is in the company's currency and the cart is priced in the
        # order's. They are the same currency today; converting costs nothing
        # and means the day they are not, the figure is still a figure in the
        # money beside it rather than two currencies added up.
        order_currency = self.currency_id
        company_currency = company.currency_id

        if cost and order_currency and company_currency and order_currency != company_currency:
            cost = company_currency._convert(
                cost, order_currency, company, fields.Date.context_today(self)
            )

        if order_currency:
            cost = order_currency.round(cost)

        return {"cost": cost, "unpriced": unpriced}

    def _aa_steel_cost_per_lb(self):
        """What a pound of spring steel COSTS us. 0 means nobody has said.

        NOT A DIVISION OF THE SELL RATE. The per-pound setting the quotes use
        is a selling price with the winding labour and the margin already
        inside it, so no arithmetic on it can recover a cost: this is a second
        figure, and the owner keeps it in Settings beside the first.

        A MISSING ROW FALLS BACK, A BAD ONE DOES NOT. The sell rate refuses to
        price at all when its parameter is gone, because quoting at cost is
        worse than quoting nothing. Nothing a customer sees is priced from this
        one, so a deleted row is answered with the figure the module ships
        with; a row that is not a number, or is zero or below, is answered with
        0 - which the caller reports as "no cost set" rather than costing a
        spring at the price of its cones alone.
        """
        raw = self.env["ir.config_parameter"].sudo().get_param(STEEL_COST_KEY)

        if raw is None or raw is False or not str(raw).strip():
            return STEEL_COST_PER_LB

        try:
            value = float(raw)
        except (TypeError, ValueError):
            _logger.warning(
                "spring_engineering: %s is %r, not a number - the cart cannot "
                "cost a spring", STEEL_COST_KEY, raw)

            return 0.0

        return value if value > 0 else 0.0

    def _aa_configured_line_cost(self, line, steel_cost):
        """What a calculator-priced line costs us, or None if it cannot be said.

        THE SALE FORMULA WITH THE COST OF STEEL IN IT. quote_assembly charges
        cones plus steel: the cones at what they cost us (there is no markup on
        them any more) and the steel at a price per pound that SELLS. Only the
        second of those is a selling figure, so the cost of the same assembly
        is the same sum with the cost per pound in its place - the same weights,
        from the same closed form, off the same specification.

        The filler is simpler still: it is already charged at cost, by the foot,
        and the line's quantity is feet.

        NONE MEANS "I CANNOT SAY", and the caller reports the line as having no
        cost set. That happens when the steel cost has not been filled in, or
        when the line carries no specification to work from - an assembly booked
        before the specification was stored, say. A spring counted at the price
        of its cones would look like a costed line and be out by a factor of
        ten.
        """
        self.ensure_one()

        template = line.product_id.product_tmpl_id
        filler = self.env.ref(FILLER_REF, raise_if_not_found=False)

        # PLASTIC FILLER: one per spring, cut to that spring's own length, so a
        # 4 ft spring takes 4 ft of filler. Charged at cost already, which is
        # why this is the same arithmetic the quote does.
        if filler and template == filler:
            return round(line.product_uom_qty * FILLER_PRICE_PER_FOOT, 2)

        spring = self.env.ref(SPRING_REF, raise_if_not_found=False)

        if not spring or template != spring:
            return None

        if not steel_cost or not line.spring_spec_json:
            return None

        # IMPORTED HERE, AND LATE, so there is ONE copy of the weight formula
        # and one copy of the density. The controller charges for the pounds
        # this computes; a second implementation in a model would be free to
        # drift from it, and the cost figure would quietly stop matching the
        # springs the shop actually winds. The import is inside the method
        # because a model module that imports a controller at load time depends
        # on the order Odoo happens to load them in.
        from ..controllers.main import _calculator_constants, _spec_weight

        try:
            spec = json.loads(line.spring_spec_json)
            springs = int(spec["springs"])
            items = spec["items"]
            density = _calculator_constants()["density"]
        except (TypeError, ValueError, KeyError):
            _logger.warning(
                "spring_engineering: line %s has a specification the cart "
                "cannot cost", line.id)

            return None

        cone_total = 0.0
        steel_weight = 0.0

        for item in items:
            try:
                wire = float(item["wire"])
                diameter = float(item["id"])
                length = float(item["length"])
            except (TypeError, ValueError, KeyError):
                return None

            # An inside diameter with no cone price is one the calculator would
            # have refused to quote. Saying nothing is the honest answer.
            if diameter not in CONE_PRICES:
                return None

            cone_total += CONE_PRICES[diameter]
            steel_weight += _spec_weight(wire, diameter, length, density)

        # ROUNDED THE WAY THE QUOTE ROUNDS IT - cones and steel to the cent
        # separately, then added - so the cost of an assembly and its price are
        # two figures built the same way and can be read side by side.
        cones = round(springs * cone_total, 2)
        steel = round(springs * steel_weight * steel_cost, 2)

        return round((cones + steel) * line.product_uom_qty, 2)
