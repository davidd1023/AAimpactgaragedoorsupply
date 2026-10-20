"""PICKUP ONLY: name, phone and email are enough.

The owner, 2026-10-20: "Checkout asks for a full address even though orders are
pickup only: street, city, zip and 'VAT'. Name, phone and email are enough for
pickup. 'VAT' doesn't apply in the US; for dealers, what matters is the Resale
Certificate."

Every order is collected at Medley. A street, a city and a zip are asked for a
delivery that does not happen, and each one is another field between a customer
and an order. So they are not required and they are not shown. VAT is not
shown at all: it is a European number, and the thing that actually takes tax
off a dealer's order here is the resale certificate, which has its own page.

WHAT IS STILL FILLED IN, QUIETLY: the country. Not for the post - for tax. This
company has two fiscal positions that apply themselves, "Domestic" for the
United States and "Foreign Trade" for anywhere else, so a customer with no
country at all would be treated as a foreign sale and charged no Florida sales
tax. Nobody is asked for it; the company's own country is put on the address
when none was given, which is the truth for somebody collecting from Medley.

The fields are HIDDEN rather than removed. Odoo's own address-form script finds
the country and state inputs and works on them when the country changes; a page
that has deleted them is a page that throws. Hidden, everything still works and
nothing is asked.
"""

from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_sale.controllers.main import WebsiteSale


class AAPickupAddress:
    """The address rules for a shop whose every order is collected."""

    def _get_mandatory_address_fields(self, country_sudo):
        """Nothing about where somebody lives is needed to pack a box for them.

        This is the set core adds to {name, email, phone} - street, city,
        country, and the state and zip a country asks for (the United States
        asks for both). Emptying it leaves exactly the three the owner named.

        It is also the set core cascades with: "if the customer provided any
        address information, they should provide their whole address". With
        nothing in it there is nothing to cascade, so a customer who does type
        a street is not then made to find their zip.
        """
        return set()

    def _complete_address_values(
        self, address_values, address_type, use_delivery_as_billing, **kwargs
    ):
        """Put the company's country on an address that came without one.

        THE TAX, not the post: "Foreign Trade" applies itself to any country
        and "Domestic" to the United States, so an address with no country
        would come out as a foreign sale with no sales tax on it.
        """
        super()._complete_address_values(
            address_values, address_type, use_delivery_as_billing, **kwargs
        )

        if not address_values.get('country_id'):
            address_values['country_id'] = request.env.company.country_id.id


class AAPickupPortal(AAPickupAddress, CustomerPortal):
    """/my/address - the same rules where a customer edits their details."""


class AAPickupShop(AAPickupAddress, WebsiteSale):
    """/shop/address - checkout, which is where the owner saw it."""
