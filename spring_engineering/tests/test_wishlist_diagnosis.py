import json
import re

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


@tagged("post_install", "-at_install")
class TestWishlistStuckRow(HttpCase):
    """The loop the owner was stuck in: a row the page cannot reach is a row
    the website cannot delete, because removing one goes through the list it
    is missing from."""

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.website = self.env["website"].search([], limit=1)
        self.product = self.env["product.product"].create({
            "name": "Stuck Roller", "type": "consu", "list_price": 5.0,
            "is_published": True, "sale_ok": True})

    def _add(self, product):
        response = self.url_open(
            "/shop/wishlist/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"product_id": product.id}}),
            headers={"Content-Type": "application/json"})

        return response.json()

    def _rows(self, product):
        return self.env["product.wishlist"].sudo().with_context(
            active_test=False).search([("product_id", "=", product.id)])

    def test_adding_the_same_product_twice_no_longer_errors(self):
        self.authenticate("admin", "admin")
        self._add(self.product)
        again = self._add(self.product)

        self.assertNotIn("error", again,
                         "the customer was shown a duplicate error")
        self.assertEqual(len(self._rows(self.product)), 1)

    def test_an_unreachable_row_is_adopted_rather_than_refused(self):
        """An archived row, or one left on another website, comes back to the
        site being browsed instead of blocking it for ever."""
        self.authenticate("admin", "admin")
        self._add(self.product)
        other = self.env["website"].create({"name": "Somewhere Else"})
        self._rows(self.product).write({"active": False, "website_id": other.id})

        again = self._add(self.product)
        row = self._rows(self.product)

        self.assertNotIn("error", again)
        self.assertEqual(len(row), 1, "a second row was created")
        self.assertTrue(row.active)
        self.assertEqual(row.website_id, self.website)
        # AND IT IS ON THE PAGE AGAIN, which is the only claim worth making:
        # current() answers from the request, so calling it here would measure
        # nothing. An earlier draft of this line asserted that the row was in
        # itself, which is true of every row ever written.
        page = self.url_open("/shop/wishlist").text
        self.assertIn(self.product.name, page)

    def test_an_unpublished_product_can_be_cleared_from_the_page(self):
        """It can never be reached - that is Odoo's rule - so it has to be
        removable from somewhere."""
        self.authenticate("admin", "admin")
        self._add(self.product)
        self.product.product_tmpl_id.write({"is_published": False})

        page = self.url_open("/shop/wishlist/diagnose").text
        self.assertIn("cannot be reached", page)

        token = re.search(r"name='csrf_token' value='([^']+)'", page).group(1)
        self.url_open("/shop/wishlist/diagnose/clear",
                      data={"csrf_token": token})

        self.assertFalse(self._rows(self.product), "the stuck row is still there")

    def test_clearing_leaves_a_working_wish_alone(self):
        self.authenticate("admin", "admin")
        self._add(self.product)
        page = self.url_open("/shop/wishlist/diagnose").text
        self.assertNotIn("cannot be reached", page,
                         "a healthy wish was offered for deletion")
