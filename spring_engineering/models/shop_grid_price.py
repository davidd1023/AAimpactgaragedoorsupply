"""THE SHOP CARD SHOWS WHAT THE PRODUCT PAGE WILL SHOW.

Owner, 2026-10-28: *"kit prices aren't matching, for example the aa-1200
hardware kit says 254.39 when you first see it on the shop page, but when you
enter its product page it says 293.97 on its default values."*

HE IS RIGHT, AND IT IS ODOO'S OWN DOING. The two numbers come from two
different methods that were never asked the same question:

  * the SHOP GRID calls `_get_sales_prices`, which prices the TEMPLATE -
    `pricelist._compute_price_rule(template, 1)` - with NO COMBINATION at
    all, so not one attribute extra is in it;
  * the PRODUCT PAGE calls `_get_combination_info`, which, given no
    combination, picks `_get_first_possible_combination()` and prices THAT
    VARIANT, extras included.

254.39 and 293.97 differ by exactly 39.58, which is what his AA-1200's
default values add. Measured, not guessed: the same gap reproduces here on a
product with one 39.58 extra, and the test fetches both pages rather than
calling the methods.

THIS IS NOT ONE KIT. Since the catalogue merge of 2026-10-21 nearly every
family in this shop is priced this way - "the merge prices a variant as the
product's price plus an extra per size" - so the grid has been under-stating
hinges, shafts, brackets and the rest as well. Nobody noticed until a kit put
forty dollars between the two screens.

THE PAGE IS THE ONE THAT IS RIGHT, so the card is moved to it. The card could
instead have been labelled "from $254.39", which is Odoo's own reading of that
number - but a customer comparing cards wants to compare what things cost,
and the first thing the shop tells them should not be a figure they can never
pay.

HOW, AND WHY NOT BY ARITHMETIC. The obvious fix is to add the extras onto the
number `_get_sales_prices` worked out. It would be wrong: that number has
already been through the pricelist, the fiscal position and the tax display
setting, and an extra is none of those things - on a tax-inclusive shop it
would land outside the tax. So the card asks `_get_combination_info` for the
very answer the page is going to give and shows that.

IT ONLY RUNS WHERE THERE IS SOMETHING TO FIX. A template with no priced
attribute value is left exactly as Odoo priced it - this is a fix for a
disagreement, not a new price - and that check is a field read, so the
catalogue does not pay for the handful of products that need it.
"""

from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _aa_has_priced_attributes(self):
        """Could this template's variants cost more than the template?

        Cheap on purpose: a field read over the attribute values, so the shop
        grid does not do real pricing work for the products that have nothing
        wrong with them.
        """
        self.ensure_one()
        values = (self.valid_product_template_attribute_line_ids
                  .product_template_value_ids)

        return any(value.price_extra for value in values)

    def _get_sales_prices(self, website):
        """Odoo's prices for the shop cards, with the default variant in them."""
        prices = super()._get_sales_prices(website)

        for template in self:
            vals = prices.get(template.id)

            if not vals or not template._aa_has_priced_attributes():
                continue

            # THE PAGE'S OWN ANSWER, asked the way the page asks it: no
            # combination, so `_get_combination_info` picks the first possible
            # one exactly as the product page will.
            shown = template._get_combination_info().get("price")
            was = vals.get("price_reduce")

            if shown is None or was is None:
                continue

            vals["price_reduce"] = shown

            # The struck-through comparison price moves with it, or the card
            # would advertise a saving that is bigger than it is.
            if vals.get("base_price"):
                vals["base_price"] += shown - was

        return prices
