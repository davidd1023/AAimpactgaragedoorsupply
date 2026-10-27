"""A KIT THAT COSTS NOTHING UNTIL YOU PUT SOMETHING IN IT CAN STILL BE BOUGHT.

Owner, 2026-10-27: *"there is a custom kit that should normally cost 0$ until
you start adding items, the problem is that the store doesnt detect that items
have been added to the kit so it still believes the price is zero, and when you
try to buy an item that costs 0$ it gives you a contact us button instead of an
add to cart button."*

THE KIT IS PRICED AT NOTHING ON PURPOSE, and that decision is not being undone
here. The parts carry the money, each on its own line (owner, 2026-10-20), so
the kit line is a heading - `custom_kit_data.xml` says as much, and putting a
price on it would charge for the kit ON TOP of the parts that make it up.

WHAT WENT WRONG IS ODOO'S ZERO-PRICE RULE, not the price. The website setting
"Hide 'Add To Cart' when price = 0" exists to stop a product nobody has priced
being sold for nothing, and it is a good rule - the shop should keep it. But it
asks the PRODUCT what it costs, and this product's answer is honestly nothing:
the money is on the lines beside it. So the page swapped Add to Cart for
Contact Us and the kit could never be bought, however much had been put in it.

Odoo enforces that rule in FIVE places and they do not share a hook, so all
five are answered here:

  * `_get_combination_info` - what the product page draws, which is where the
    Contact Us button came from;
  * `_is_add_to_cart_allowed` - the server's own refusal, so a page that did
    show the button would be told no at the last moment;
  * `_website_show_quick_add`, on the template and on the variant - the quick
    add button in the shop grid;
  * `sale.order.line._check_validity` - raised while adding;
  * `sale.order._get_zero_priced_lines` - which blocks CHECKOUT, and would
    have stranded a full cart at the payment step.

Finding four of them and missing the fifth would have been worse than finding
none: the customer would get further each time and still not be able to pay.

IT IS EXEMPT ONLY FOR THE CUSTOM KIT. `aa_custom_kit` is one boolean on one
product. Every other zero-priced product in the shop is still refused, which is
what the setting is for.
"""

from odoo import models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _aa_sells_at_zero(self):
        """Is this a product whose own price is honestly nothing?

        One line, so that the five overrides below cannot drift apart, and so
        that another such product is one flag rather than five edits.
        """
        return bool(self.aa_custom_kit)

    def _get_combination_info(self, *args, **kwargs):
        """The product page. THIS IS THE CONTACT US BUTTON.

        Odoo sets `prevent_zero_price_sale` here and the template reads it to
        decide between Add to Cart and Contact Us - and to hide the quantity
        box with it, so even a page edited by hand could not have got round it.
        """
        info = super()._get_combination_info(*args, **kwargs)

        if info.get("prevent_zero_price_sale") and self._aa_sells_at_zero():
            info["prevent_zero_price_sale"] = False

        return info

    def _website_show_quick_add(self):
        if self._aa_sells_at_zero():
            return bool(self.filtered_domain(
                self.env["website"]._product_domain()))

        return super()._website_show_quick_add()


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _is_add_to_cart_allowed(self):
        """The server's own refusal, behind the button.

        Checked before super() rather than after, because super() returns
        False for exactly the reason being excused - there would be nothing
        left to tell apart.
        """
        if self.product_tmpl_id._aa_sells_at_zero():
            if not self.active or not self.website_published:
                return False

            if not self.filtered_domain(self.env["website"]._product_domain()):
                return False

            return request.website.has_ecommerce_access()

        return super()._is_add_to_cart_allowed()

    def _website_show_quick_add(self):
        if self.product_tmpl_id._aa_sells_at_zero():
            return bool(self.filtered_domain(
                self.env["website"]._product_domain()))

        return super()._website_show_quick_add()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _check_validity(self):
        """Raised while the line is being added."""
        if self.product_template_id._aa_sells_at_zero():
            return

        return super()._check_validity()


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_zero_priced_lines(self):
        """THE ONE THAT WOULD HAVE BEEN MISSED, and the worst to miss.

        It is not about adding to the cart at all - it is the check that
        stops a cart being PAID FOR. Without this the customer gets the
        button, gets the kit and its parts into the cart, and is then refused
        at the payment step with nothing on the screen to tell them why.
        """
        lines = super()._get_zero_priced_lines()

        return lines.filtered(
            lambda line: not line.product_template_id._aa_sells_at_zero())
