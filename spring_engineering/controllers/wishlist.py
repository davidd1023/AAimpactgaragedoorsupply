from odoo import http
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale_wishlist.controllers.main import WebsiteSaleWishlist


class Wishlist(WebsiteSaleWishlist):
    """Clicking the heart must never end in a validation error.

    THE LOOP THE OWNER IS STUCK IN. A wishlist row is found by partner AND by
    the website being browsed, and only if the product is still published -
    but the database rule that forbids a second one looks at the product and
    the partner alone. So a row that the page cannot reach is a row nobody can
    delete either: the heart draws itself empty, clicking it tries to ADD, and
    the add is refused as a duplicate. The customer is told the product is
    already on a wishlist that is demonstrably empty, and there is no way out
    of it from the website at all.

    So an add that finds its own row ADOPTS it rather than failing: it is
    brought back to the website being browsed, unarchived, and repriced. The
    heart fills, the row is reachable, and clicking again removes it the
    ordinary way.

    NOT A WAY ROUND THE PUBLISHED RULE. An unpublished product still does not
    appear on the wishlist page - that is Odoo's rule and a deliberate one.
    What changes is that the customer is no longer shown an error about a
    duplicate they cannot see or remove.
    """

    @http.route()
    def add_to_wishlist(self, product_id, **kw):
        # The public path cannot hit this: a signed-out visitor's rows carry no
        # partner, and the uniqueness rule treats every one of those as
        # distinct. Only a signed-in customer can be refused.
        if request.website.is_public_user():
            return super().add_to_wishlist(product_id, **kw)

        partner = request.env.user.partner_id
        existing = request.env["product.wishlist"].sudo().with_context(
            active_test=False,
        ).search([
            ("partner_id", "=", partner.id),
            ("product_id", "=", product_id),
        ], limit=1)

        if not existing:
            return super().add_to_wishlist(product_id, **kw)

        product = request.env["product.product"].browse(product_id)
        existing.write({
            "active": True,
            "website_id": request.website.id,
            "pricelist_id": request.pricelist.id,
            "currency_id": request.website.currency_id.id,
            "price": product._get_combination_info_variant()["price"],
        })

        return existing

    @http.route("/shop/wishlist/remove_product", type="jsonrpc", auth="public",
                website=True)
    def remove_product_from_wishlist(self, product_id, product_tmpl_id=None,
                                     **kw):
        """Take a product off the wishlist, found by the product.

        A PRODUCT CARD KNOWS NO ROW ID. Odoo removes a wish by its own id,
        which the wishlist page has and the shop does not - so the shop could
        add and never take away. This finds the row the same way the page that
        lists it does, and then hands it to Odoo's own route so the session
        bookkeeping a signed-out visitor depends on is done once, there.

        ARCHIVED ROWS INCLUDED. A row the page cannot reach is exactly the one
        somebody needs to clear, and refusing to look at it would leave the
        heart stuck red with no way back.

        AND THE TEMPLATE AS A SECOND CHANCE. One card is one heart for a whole
        product, and Odoo reddens it when ANY of its variants is on the list
        while still offering the first variant's id. Asked by that id alone
        the search finds nothing, so the heart would empty itself and the row
        would stay - the very "removing does not work" this route exists to
        end. A card may therefore name its template as well, and the row is
        found by it when the variant does not match. A product page may not:
        it is showing one variant, and the row it offers to take off is that
        variant's or none at all.
        """
        Wish = request.env["product.wishlist"].sudo().with_context(
            active_test=False)

        if request.website.is_public_user():
            whose = [("id", "in", request.session.get("wishlist_ids") or [])]
        else:
            whose = [("partner_id", "=", request.env.user.partner_id.id)]

        wish = Wish.search(whose + [("product_id", "=", product_id)], limit=1)

        if not wish and product_tmpl_id:
            wish = Wish.search(
                whose + [("product_id.product_tmpl_id", "=", product_tmpl_id)],
                limit=1)

        if not wish:
            return True

        return self.remove_from_wishlist(wish.id)

    @http.route("/shop/wishlist/state", type="jsonrpc", auth="public",
                website=True)
    def wishlist_state(self, **kw):
        """Everything the browser needs to draw a heart, in one answer.

        TWO QUESTIONS, NOT ONE. Odoo's own route answers "which products are
        on the list", which is all its buttons need because they are never
        clicked twice. A heart that toggles has to answer a second one: WHICH
        VARIANT of this product is the one on the list - because a shop card
        stands for the whole template and offers the first variant, while the
        row on the wishlist may well be for another. Without the mapping the
        card compares its own variant against a list that holds a different
        one, finds nothing, and draws itself empty next to a wishlist that has
        the product in it.
        """
        state = {"ids": [], "variants": {}}

        for wish in request.env["product.wishlist"].current():
            state["ids"].append(wish.product_id.id)
            # One per template: a card is one heart, so it can only offer to
            # take one row off. Two variants of the same product on the list
            # leaves the card red until both are gone, which is the same thing
            # Odoo's own card says by being red for the template at all.
            state["variants"].setdefault(
                str(wish.product_id.product_tmpl_id.id), wish.product_id.id)

        return state


class ShopCardsKnowTheirVariant(WebsiteSale):
    """Which variant each wishlisted card is for.

    ODOO PUTS THE WORD "True" WHERE THE ID SHOULD BE. Its card template picks
    the variant like this:

        <t t-set="in_wish" t-value="product in products_in_wishlist"/>
        <t t-set="product_variant_id"
           t-value="in_wish or product._get_first_possible_variant_id()"/>

    in_wish is a BOOLEAN, so a product already on the wishlist renders
    data-product-product-id="True". Nothing can act on that: parseInt gives
    NaN, and the handler - Odoo's or this module's - has no product to work
    with.

    It never mattered to Odoo, because its own button is disabled in exactly
    that state, so the attribute is never read. Making the heart clickable is
    what exposed it, and it is the whole of the bug the owner kept hitting:
    adding worked and removing did not, removing worked right after adding
    because the page still held the real id in the DOM, and any re-render -
    another page, another category - brought the word "True" back and the
    heart died again.

    So the page is told which variant each wishlisted template is for, and the
    template reads that instead of the boolean.
    """

    def _get_additional_shop_values(self, values, **kwargs):
        vals = super()._get_additional_shop_values(values, **kwargs)
        vals["aa_wishlisted_variants"] = {
            wish.product_id.product_tmpl_id.id: wish.product_id.id
            for wish in request.env["product.wishlist"].current()
        }

        return vals
