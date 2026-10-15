from odoo.http import request

from odoo.addons.website_sale.controllers.cart import Cart


class TrackPreparationCart(Cart):
    """The little "added to your cart" popup has to quote the same price the
    product page did.

    A PREPARED TRACK IS NOT ONE LINE. Picking Prepared adds a flag angle and a
    set of jamb brackets as lines of their own, and the popup lists only the
    line the customer clicked - so it showed the bare track's price while the
    page right behind it showed the prepared one. The same was true of a
    hardware kit ordered with springs, tracks or cables.

    The parts are folded INTO the line they belong to rather than listed
    beside it: the customer chose a prepared track, not five things, and the
    popup is a confirmation rather than a cart.
    """

    def _get_cart_notification_information(self, order, added_qty_per_line):
        information = super()._get_cart_notification_information(
            order, added_qty_per_line)
        rows = information.get("lines") or []

        if not rows:
            return information

        # TAX THE SAME WAY THE POPUP DOES, which is the website's own setting -
        # the figure added here has to be in the same money as the one it is
        # added to.
        show_tax = (
            order.website_id.show_line_subtotals_tax_selection == "tax_included")
        shown = {row["id"] for row in rows}

        for row in rows:
            line = order.order_line.browse(row["id"]).exists()

            if not line:
                continue

            extra = self._cart_notification_extra(line, show_tax, shown)

            if extra:
                row["price_total"] += extra * row["quantity"]

        return information

    def _cart_notification_extra(self, line, show_tax, shown):
        """What this line's own parts add, per one of it.

        ONLY WHAT IS NOT ALREADY ON SCREEN. A combo's choices are listed as
        rows in their own right, so adding them to the parent as well would
        count them twice; anything already shown is left alone, and so is a
        combo item whatever else happens.
        """
        parts = line.order_id.order_line.filtered(
            lambda l: (
                l.id not in shown
                and not l.combo_item_id
                and (l.track_prep_parent_id == line or l.linked_line_id == line)
            )
        )

        if not parts or not line.product_uom_qty:
            return 0.0

        # THE PARTS' OWN LINE TOTALS, not their unit price times quantity.
        # A line's total is rounded to the currency, so four brackets at 1.197
        # bill 4.79 and not 4.788 - and multiplying the rounded UNIT price
        # (1.20) by four instead gives 4.80, which is how the popup came out
        # two cents above the cart it was describing.
        total = sum(
            (part.price_total if show_tax else part.price_subtotal)
            for part in parts
        )

        # PER ONE TRACK, because the popup multiplies by the quantity added.
        # The parts' quantities already follow the track's, so dividing by it
        # is what turns four brackets for two tracks back into two for one.
        return total / line.product_uom_qty

    # --- reordering a whole order from the cart -------------------------------
    #
    # ODOO'S QUICK REORDER OFFERS PRODUCTS, NOT ORDERS. Its panel lists the
    # lines of the last ten confirmed orders, grouped by day, to be added one
    # at a time - and the button that opens it is DISABLED when that list comes
    # back empty, which is why it looked like it did nothing at all.
    #
    # What the owner asked for is the other shape: show the orders, pick one,
    # and have everything on it in the cart. The adding already exists -
    # /my/orders/reorder walks an order's lines and adds each one - so this is
    # the half that was missing: which orders to offer.
    # EVERY ORDER, NOT THE LAST TEN. Odoo's own history stops at ten and the
    # owner asked to see the rest; the panel scrolls, so the list can be as
    # long as the account is old. The cap is a guard against a page that never
    # finishes rendering for somebody with thousands, not a limit anybody is
    # expected to meet - and the panel says so when it bites.
    AA_REORDER_LIMIT = 250

    def _aa_previous_orders(self):
        """The customer's own finished orders, newest first."""
        if request.website.is_public_user():
            return request.env["sale.order"].browse()

        return request.env["sale.order"].sudo().search(
            [
                ("partner_id", "=", request.env.user.partner_id.id),
                # CONFIRMED, WHICH IN THIS VERSION IS THE WHOLE STORY. An
                # earlier draft of this also allowed 'done', on the assumption
                # that a locked order sits in a state of its own - it does not.
                # Odoo 19 keeps a locked order at 'sale' and records the lock
                # in a separate flag, so asking for 'done' asks for a state no
                # sale order can be in.
                ("state", "=", "sale"),
                # AND ONE TAKEN OVER THE PHONE IS STILL YOURS. Odoo filters the
                # history to orders placed on this website, which hides every
                # order the office entered in the back end - those carry no
                # website at all.
                ("website_id", "in", (False, request.website.id)),
            ],
            order="date_order desc, id desc",
            limit=self.AA_REORDER_LIMIT,
        )

    def _cart_values(self, **post):
        """The documented hook for extra values on the cart page."""
        values = super()._cart_values(**post)
        values["aa_reorder_orders"] = self._aa_previous_orders()

        return values
