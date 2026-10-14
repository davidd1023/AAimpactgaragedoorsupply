from odoo import http
from odoo.http import request

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
    def remove_product_from_wishlist(self, product_id, **kw):
        """Take a product off the wishlist, found by the product.

        A PRODUCT CARD KNOWS NO ROW ID. Odoo removes a wish by its own id,
        which the wishlist page has and the shop does not - so the shop could
        add and never take away. This finds the row the same way the page that
        lists it does, and then hands it to Odoo's own route so the session
        bookkeeping a signed-out visitor depends on is done once, there.

        ARCHIVED ROWS INCLUDED. A row the page cannot reach is exactly the one
        somebody needs to clear, and refusing to look at it would leave the
        heart stuck red with no way back.
        """
        Wish = request.env["product.wishlist"].sudo().with_context(
            active_test=False)

        if request.website.is_public_user():
            wish = Wish.search([
                ("id", "in", request.session.get("wishlist_ids") or []),
                ("product_id", "=", product_id),
            ], limit=1)
        else:
            wish = Wish.search([
                ("partner_id", "=", request.env.user.partner_id.id),
                ("product_id", "=", product_id),
            ], limit=1)

        if not wish:
            return True

        return self.remove_from_wishlist(wish.id)
