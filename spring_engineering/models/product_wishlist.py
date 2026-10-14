from odoo import api, models
from odoo.http import request


class ProductWishlist(models.Model):
    _inherit = "product.wishlist"

    @api.model
    def current(self):
        """The wishlist, with one inconsistency of Odoo's taken out.

        THE HEART THAT WOULD NOT STAY RED. Odoo drops any wish whose product
        is not published, from the wishlist page, from the ids the browser
        keeps and from the marks on the shop's cards - while showing the shop
        itself to an internal user complete with its unpublished products,
        letting them put one in a cart, and letting them wishlist it. The
        result is a heart that fills on the click and is empty on the next
        page, for some products and not others, which is exactly how it was
        reported: sometimes they stay, sometimes they go back.

        It tracked publication, not luck. A published product is in both
        lists; an unpublished one is in neither.

        SO THE RULE IS RELAXED FOR INTERNAL USERS ONLY, who are the only
        people who can see an unpublished product in the shop in the first
        place. Nothing changes for a customer: their wishlist still holds only
        what is published, which is Odoo's rule and the right one - you cannot
        buy what is not for sale, and a wishlist full of things that cannot be
        bought is worse than one that is short.

        The real fix is still to publish the products. This only stops the
        shop contradicting itself while somebody is working through them.
        """
        wishes = super().current()

        if not request or not self.env.user._is_internal():
            return wishes

        if request.website.is_public_user():
            return wishes

        mine = self.search([
            ("partner_id", "=", self.env.user.partner_id.id),
            ("website_id", "=", request.website.id),
        ])

        # The other half of Odoo's filter is kept: a product that cannot be
        # added to a cart at all is still not something to offer.
        return mine.filtered(
            lambda wish: wish.sudo().product_id.product_tmpl_id
            ._is_add_to_cart_possible()
        )
