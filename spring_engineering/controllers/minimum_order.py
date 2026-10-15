from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class MinimumOrder(WebsiteSale):
    """A cart under the minimum cannot walk past the cart page.

    THE BUTTON BEING DISABLED IS NOT THE RULE, it is how the rule looks. Odoo
    disables that button from _is_cart_ready, which this module answers, and
    the payment routes refuse an order that is not ready - but /shop/checkout
    is a URL, and a customer who has it in their history, or who presses Back
    from a cart they have since emptied, arrives there without pressing
    anything. Odoo already has the right shape for this: _check_cart returns a
    redirect for a cart that cannot proceed, and every checkout step asks it
    first. So the answer is sent back to the cart, which is the one page that
    explains what is missing and is the only place it can be fixed.
    """

    def _check_cart(self, order_sudo):
        redirection = super()._check_cart(order_sudo)

        if redirection:
            return redirection

        if order_sudo._aa_minimum_shortfall():
            return request.redirect("/shop/cart")
