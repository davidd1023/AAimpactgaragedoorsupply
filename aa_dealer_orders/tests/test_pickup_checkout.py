"""PICKUP ONLY: name, phone and email are enough.

The owner, 2026-10-20: "Checkout asks for a full address even though orders are
pickup only: street, city, zip and 'VAT'. Name, phone and email are enough for
pickup. 'VAT' doesn't apply in the US; for dealers, what matters is the Resale
Certificate."
"""

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class PickupCheckoutCase(HttpCase):

    def setUp(self):
        super().setUp()
        self.shop = self.env["product.template"].create({
            "name": "Pickup Test Bracket", "type": "consu",
            "list_price": 10.0, "is_published": True})

    def _post_address(self, **fields):
        """The address form as the browser posts it, token and all."""
        import re

        page = self.url_open("/shop/address").text
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)

        self.assertTrue(token, "the address form was not reached")
        values = {
            "name": "Hector the Fitter",
            "email": "hector@example.com",
            "phone": "786-555-0101",
            "address_type": "billing",
            "use_delivery_as_billing": "1",
            "required_fields": "name,email",
            "csrf_token": token.group(1),
        }
        values.update(fields)

        return self.url_open("/shop/address/submit", data=values)

    def _cart(self):
        """Something in the cart, or /shop/address sends you back to the shop."""
        import json

        self.url_open(
            "/shop/cart/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
                "product_template_id": self.shop.id,
                "product_id": self.shop.product_variant_ids[:1].id,
                "quantity": 1}}),
            headers={"Content-Type": "application/json"})

    # --- what is asked for -----------------------------------------------------

    def test_three_fields_are_enough(self):
        """THE WHOLE REQUEST. A name, a phone number and an email address, and
        the order can be placed - no street, no city, no zip."""
        self._cart()
        response = self._post_address()

        self.assertEqual(response.status_code, 200)
        partner = self.env["res.partner"].search(
            [("email", "=", "hector@example.com")], limit=1)

        self.assertTrue(partner, "the address was refused")
        # Odoo tidies the number into "+1 786-555-0101" - which it can only do
        # because the country got filled in, so this is the country default
        # showing up in passing.
        self.assertIn("786-555-0101", partner.phone)
        self.assertFalse(partner.street)
        self.assertFalse(partner.zip)

    def test_the_rule_set_is_the_three_fields(self):
        """THE RULE ITSELF. Core builds {name, email, phone} and then adds
        street, city, country - and the state and zip the United States asks
        for - from _get_mandatory_address_fields. Emptying that set is the
        whole change, and this reads it back.

        Asserted on the mixin rather than on a live controller: a controller's
        own _needs_address reads `request`, so one cannot be asked anything
        outside a request ("object is not bound").
        """
        from odoo.addons.aa_dealer_orders.checkout import AAPickupAddress

        united_states = self.env.ref("base.us")

        self.assertTrue(united_states.zip_required, "the fixture is wrong")
        self.assertTrue(united_states.state_required)
        self.assertEqual(
            AAPickupAddress._get_mandatory_address_fields(None, united_states),
            set())

    def test_the_customer_reaches_the_payment_step(self):
        """WHAT IT IS ALL FOR: three fields, and the order can be paid for.
        This is the check that used to send a pickup customer back to the
        address form looking for a zip."""
        self._cart()
        self._post_address()
        page = self.url_open("/shop/checkout")

        self.assertEqual(page.status_code, 200)
        self.assertNotIn("Some required fields are empty", page.text)

    # --- the country, which is about tax rather than post ----------------------

    def test_the_company_country_is_filled_in_for_them(self):
        """NOT FOR THE POST - FOR THE TAX. This company has two fiscal
        positions that apply themselves: "Domestic" for the United States and
        "Foreign Trade" for anywhere else. An address with no country at all
        comes out as a foreign sale with no Florida sales tax on it, so the
        company's own country is put on an address that arrives without one.
        """
        self._cart()
        self._post_address(email="country@example.com")
        partner = self.env["res.partner"].search(
            [("email", "=", "country@example.com")], limit=1)

        self.assertEqual(partner.country_id, self.env.company.country_id)
        self.assertTrue(partner.country_id, "the company has no country set")

    def test_a_pickup_customer_is_not_treated_as_a_foreign_sale(self):
        """The consequence of the above, asserted where it actually bites."""
        self._cart()
        self._post_address(email="tax@example.com")
        partner = self.env["res.partner"].search(
            [("email", "=", "tax@example.com")], limit=1)
        position = self.env["account.fiscal.position"].with_company(
            self.env.company)._get_fiscal_position(partner)
        foreign = self.env["account.fiscal.position"].search(
            [("name", "ilike", "Foreign")], limit=1)

        if foreign:
            self.assertNotEqual(
                position, foreign,
                "a customer collecting from Medley was billed as an export")

    # --- what the page shows ---------------------------------------------------

    def test_the_form_does_not_ask_for_an_address_or_a_vat_number(self):
        """Hidden rather than deleted: Odoo's own script reaches for the
        country and state inputs when the country changes, and a form that has
        removed them is a form that throws. So the inputs are all still there
        and all carry d-none."""
        from lxml import html

        self._cart()
        page = html.fromstring(self.url_open("/shop/address").text)

        for field in ("div_street", "div_city", "div_zip", "div_country",
                      "div_state", "div_vat"):
            node = page.get_element_by_id(field, None)

            with self.subTest(field=field):
                self.assertIsNotNone(node, "%s was removed, not hidden" % field)
                self.assertIn("d-none", node.get("class") or "",
                              "%s is still being asked for" % field)

        for field in ("div_name", "div_email", "div_phone"):
            node = page.get_element_by_id(field, None)

            with self.subTest(field=field):
                self.assertIsNotNone(node)
                self.assertNotIn("d-none", node.get("class") or "",
                                 "%s is hidden, and it is one of the three" % field)

    def test_the_form_points_a_dealer_at_the_resale_certificate(self):
        """"for dealers, what matters is the Resale Certificate" - so where
        VAT used to be, the page says so."""
        self._cart()
        page = self.url_open("/shop/address").text

        self.assertIn("resale certificate", page.lower())
