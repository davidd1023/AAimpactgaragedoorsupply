from odoo import fields, models


class SaleOrder(models.Model):
    """WHAT THE CART COSTS US, shown to staff and to nobody else.

    A member of staff looking at a cart - their own, or one they are building
    for a customer on the phone - is asked a question the page cannot answer:
    is this order worth taking? The sale price is on the screen; the cost is
    on each product's form, one product at a time, which is no use while the
    cart is in front of you.

    So the cart adds up the Cost field of what is in it and prints the figure
    under the Total. It is the same number the product form calls Cost
    (`standard_price`), summed over every line - nothing is inferred and no
    margin is applied, because a figure that was arrived at by a calculation
    of ours would be a different claim from the one the product form makes.
    """

    _inherit = "sale.order"

    def _aa_cart_cost(self):
        """The cart's production cost, or None for anyone not on the staff.

        Returns ``{"cost": float, "unpriced": int}``:

          * ``cost`` - the sum of Cost x quantity, in the ORDER's currency.
          * ``unpriced`` - how many lines carry no cost at all, so the page
            can say so. A product whose Cost is blank contributes nothing,
            and a total that is quietly short is worse than no total: it
            reads like a real cost and it is not one. Custom springs, custom
            kits and anything else priced by the calculator are the likely
            candidates, because their price is worked out at add-to-cart time
            and never written back to a product's Cost field.

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

        for line in self.order_line:
            # Sections, notes and the shipping line are not goods. Delivery in
            # particular has no cost of its own to speak of, and counting it as
            # a product with a blank cost would raise a warning about a line
            # that was never going to have one.
            if line.display_type or line.is_delivery or not line.product_id:
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
