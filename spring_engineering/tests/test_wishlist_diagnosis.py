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


@tagged("post_install", "-at_install")
class TestWishlistButtonAlwaysThere(HttpCase):
    """A customer cannot find a wishlist that only appears once they have used
    it. Odoo hides the header heart when the count is zero; this shop does not.
    """

    def test_the_header_keeps_the_wishlist_link_when_it_is_empty(self):
        self.assertFalse(
            self.env.ref(
                "website_sale_wishlist.header_hide_empty_wishlist_link"
            ).active,
            "the hide-when-empty view is back on")

        page = self.url_open("/shop").text
        self.assertIn("/shop/wishlist", page,
                      "a visitor with an empty wishlist has no way to reach it")

    def test_the_count_itself_is_still_hidden_at_zero(self):
        """The BUTTON stays; the little number on it does not sit there
        reading zero."""
        page = self.url_open("/shop").text
        self.assertIn("my_wish_quantity", page)
        self.assertIn("d-none", page)


@tagged("post_install", "-at_install")
class TestWishlistHeartOnTheCard(HttpCase):
    """The heart on a product card has to say what it knows.

    Odoo renders it filled for a product already wishlisted - and renders it
    DISABLED, so there is no way to take the product off the list from the
    shop. The owner wants a toggle: red when it is on the list, and clicking
    it takes it off.
    """

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.product = self.env["product.product"].create({
            "name": "Heart Probe Roller", "type": "consu", "list_price": 5.0,
            "is_published": True, "sale_ok": True})

    def _card(self, page):
        """The product card's wishlist button, as served."""
        hit = re.search(
            r"<button[^>]*o_add_wishlist[^>]*data-product-product-id=\"%s\"[^>]*>"
            % self.product.id, page)

        if not hit:
            hit = re.search(
                r"<button[^>]*data-product-product-id=\"%s\"[^>]*o_add_wishlist[^>]*>"
                % self.product.id, page)

        return hit.group(0) if hit else ""

    def test_the_heart_is_filled_on_a_fresh_page_load(self):
        self.authenticate("admin", "admin")
        self.url_open(
            "/shop/wishlist/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"product_id": self.product.id}}),
            headers={"Content-Type": "application/json"})

        page = self.url_open("/shop?search=Heart Probe").text
        print("\nPRODUCT ON THE PAGE:", self.product.name in page)
        print("WISHLIST BUTTONS:", page.count("o_add_wishlist"))
        here = page.find("Heart Probe Roller")
        print("AROUND THE CARD:", " ".join(page[max(0, here - 1400):here].split())[-700:])
        self.assertIn("o_in_wishlist", page)


@tagged("post_install", "-at_install")
class TestWishlistToggleTour(HttpCase):
    """The two things the owner asked for, in a real browser.

    Both are about what happens between page loads and on a second click, and
    no server-side test can see either.
    """

    def test_the_heart_stays_red_and_clicking_it_removes(self):
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.env["product.product"].create({
            "name": "Heart Probe Roller", "type": "consu", "list_price": 5.0,
            "is_published": True, "sale_ok": True})
        self.env["product.wishlist"].sudo().search([]).unlink()

        try:
            self.start_tour("/shop?search=Heart+Probe+Roller",
                            "aa_wishlist_toggle", login="admin")
        except RuntimeError as error:
            # THE SANDBOX, NOT THE TOUR. This container cannot spawn the
            # thread the headless browser talks over - "can't start new
            # thread" - so the tour cannot run HERE. It is kept, and skipped
            # with the reason said out loud, because a test that quietly
            # passes when it never ran is worse than one that is absent. Any
            # other error is a real failure and is left to fail.
            if "can't start new thread" not in str(error):
                raise

            self.skipTest("no browser available in this container: %s" % error)


@tagged("post_install", "-at_install")
class TestWishlistToggleServerSide(HttpCase):
    """What the browser needs from the server for the heart to be a switch."""

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.product = self.env["product.product"].create({
            "name": "Toggle Probe Roller", "type": "consu", "list_price": 5.0,
            "is_published": True, "sale_ok": True})

    def _add(self, product):
        return self.url_open(
            "/shop/wishlist/add",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"product_id": product.id}}),
            headers={"Content-Type": "application/json"}).json()

    def _remove(self, product):
        return self.url_open(
            "/shop/wishlist/remove_product",
            data=json.dumps({"jsonrpc": "2.0", "method": "call",
                             "params": {"product_id": product.id}}),
            headers={"Content-Type": "application/json"}).json()

    def _rows(self, product):
        return self.env["product.wishlist"].sudo().with_context(
            active_test=False).search([("product_id", "=", product.id)])

    def test_the_card_button_is_not_served_disabled(self):
        """Odoo disables it once the product is on the list, which is also how
        it colours it red. This shop colours it from the class instead, so the
        button stays clickable - and that is the whole of the second half of
        what was asked for."""
        self.authenticate("admin", "admin")
        self._add(self.product)
        page = self.url_open("/shop?search=Toggle+Probe").text
        card = re.search(r"<button[^>]*o_add_wishlist[^>]*>", page).group(0)

        self.assertIn("o_in_wishlist", card, card)
        self.assertNotIn("disabled", card, card)

    def test_a_signed_in_customer_can_remove_by_product(self):
        self.authenticate("admin", "admin")
        self._add(self.product)
        self.assertTrue(self._rows(self.product))

        self._remove(self.product)
        self.assertFalse(self._rows(self.product), "the row is still there")

    def test_a_signed_out_visitor_can_remove_by_product(self):
        """The session list a visitor's wishlist lives in has to be kept in
        step, which is why this hands the row to Odoo's own route."""
        self._add(self.product)
        self.assertTrue(self._rows(self.product))

        self._remove(self.product)
        self.assertFalse(self._rows(self.product))

    def test_removing_something_that_is_not_there_says_nothing(self):
        self.authenticate("admin", "admin")
        answer = self._remove(self.product)

        self.assertNotIn("error", answer)

    def test_a_stuck_row_can_be_removed_by_the_heart(self):
        """An archived row is exactly the one somebody needs to clear."""
        self.authenticate("admin", "admin")
        self._add(self.product)
        self._rows(self.product).write({"active": False})

        self._remove(self.product)
        self.assertFalse(self._rows(self.product))
