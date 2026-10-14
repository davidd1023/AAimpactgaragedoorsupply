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
