import json

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWishlistDiagnosis(HttpCase):
    """The page has to name the right reason, and only for an administrator.

    Three different states of the data produce the same four symptoms on the
    shop - the badge empties, the page lists nothing, and adding the product
    again is refused as a duplicate - so a page that guessed between them
    would be worse than no page at all.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.website = self.env["website"].search([], limit=1)
        self.product = self.env["product.product"].create({
            "name": "Diagnosis Roller", "type": "consu", "list_price": 5.0,
            "is_published": True, "sale_ok": True})

    def _wish(self, product):
        self.url_open(
            "/shop/wishlist/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"product_id": product.id}}),
            headers={"Content-Type": "application/json"})

        return self.env["product.wishlist"].sudo().search(
            [("product_id", "=", product.id)], limit=1)

    def _page(self):
        response = self.url_open("/shop/wishlist/diagnose")
        self.assertEqual(response.status_code, 200)

        return response.text

    def test_a_healthy_row_is_reported_as_healthy(self):
        self.authenticate("admin", "admin")
        self._wish(self.product)
        page = self._page()
        self.assertIn("Diagnosis Roller", page)
        self.assertIn("it is on the page", page)

    def test_an_archived_row_says_so(self):
        self.authenticate("admin", "admin")
        self._wish(self.product).write({"active": False})
        self.assertIn("archived", self._page())

    def test_a_row_from_another_website_says_so(self):
        other = self.env["website"].create({"name": "Second Site"})
        self.authenticate("admin", "admin")
        self._wish(self.product).write({"website_id": other.id})
        page = self._page()
        self.assertIn("saved against website", page)
        self.assertIn("Second Site", page)

    def test_an_unpublished_product_says_so(self):
        self.authenticate("admin", "admin")
        wish = self._wish(self.product)
        wish.product_id.product_tmpl_id.write({"is_published": False})
        self.assertIn("not published", self._page())

    def test_it_counts_what_signed_out_visitors_left_behind(self):
        self.authenticate("admin", "admin")
        self._wish(self.product)
        self.assertIn("row(s) belong to signed-out visitors", self._page())

    def test_an_ordinary_user_cannot_open_it(self):
        """It lists what people have wishlisted, which is not everybody's
        business."""
        self.env["res.users"].create({
            "name": "Shop Clerk", "login": "wishlist-clerk",
            "password": "wishlist-clerk",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        self.authenticate("wishlist-clerk", "wishlist-clerk")
        self.assertNotEqual(
            self.url_open("/shop/wishlist/diagnose").status_code, 200)
