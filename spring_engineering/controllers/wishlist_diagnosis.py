from markupsafe import Markup, escape

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class WishlistDiagnosis(http.Controller):
    """Why a wishlisted product is not on the wishlist page.

    A DIAGNOSTIC, AND DELETABLE. The wishlist itself is Odoo's, and the code
    is sound - a published product, a prepared track and a zero-priced one all
    round-trip correctly on a test build. What breaks it is the DATA, and three
    different states produce exactly the same four symptoms the owner
    described: the badge empties on the next page, the page lists nothing, and
    adding the product again is refused as a duplicate.

      archived         the row has active = false. The ORM hides archived rows
                       by itself; the database rule that refuses a second one
                       does not look at active.
      another website  the lookup filters on the website being browsed, while
                       the uniqueness rule is on (product, partner) and
                       ignores the website entirely.
      unpublished      the lookup drops any wish whose product is no longer
                       published, or can no longer be added to a cart.

    Guessing between them from the outside is how a correct wishlist gets
    "fixed" into a broken one, so this reads the rows and says which it is.
    Read-only, administrators only, and safe to delete once the answer is in.
    """

    @http.route("/shop/wishlist/diagnose", type="http", auth="user",
                website=True, sitemap=False)
    def diagnose(self, **kwargs):
        if not request.env.user.has_group("base.group_system"):
            raise AccessError(request.env._("Administrators only."))

        partner = request.env.user.partner_id
        website = request.website
        Wish = request.env["product.wishlist"].sudo().with_context(
            active_test=False)
        rows = Wish.search([("partner_id", "=", partner.id)], order="id")
        orphans = Wish.search([("partner_id", "=", False)], order="id")
        visible = request.env["product.wishlist"].current()

        body = [Markup("<h2>Wishlist diagnosis</h2><p>Signed in as %s "
                       "(partner #%s), browsing %s (website #%s).<br/>"
                       "%s row(s) carry your name, %s of them reach the page. "
                       "%s row(s) belong to signed-out visitors.</p>") % (
            partner.name, partner.id, website.name, website.id,
            len(rows), len(visible), len(orphans))]

        body.append(Markup(
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<tr><th>row</th><th>product</th><th>website</th>"
            "<th>why it is not on the page</th></tr>"))

        for row in rows:
            template = row.product_id.product_tmpl_id
            why = []

            if not row.active:
                why.append("archived (active = false)")

            if row.website_id != website:
                why.append("saved against website #%s (%s)" % (
                    row.website_id.id, row.website_id.name or "deleted"))

            if not template.website_published:
                why.append("product is not published")
            elif not template._is_add_to_cart_possible():
                why.append("product cannot be added to a cart")

            body.append(Markup("<tr><td>%s</td><td>%s</td><td>%s</td>"
                               "<td>%s</td></tr>") % (
                row.id, row.product_id.display_name, row.website_id.id,
                "; ".join(why) or "nothing - it is on the page"))

        body.append(Markup("</table>"))

        # AND A WAY OUT. A row the page cannot reach is a row the website
        # cannot delete, because removing one goes through the list it is
        # missing from. Clicking the heart again now adopts such a row rather
        # than failing, which is the ordinary way out - but a product that
        # stays unpublished can never be reached at all, and those rows have to
        # be clearable from somewhere.
        unreachable = rows - visible

        if unreachable:
            body.append(Markup(
                "<form method='post' action='/shop/wishlist/diagnose/clear'>"
                "<input type='hidden' name='csrf_token' value='%s'/>"
                "<p><button type='submit'>Remove the %s row(s) above that "
                "cannot be reached</button> - yours only, and nobody else's."
                "</p></form>") % (request.csrf_token(), len(unreachable)))

        return request.make_response(
            Markup("<html><body style='font-family: Arial, sans-serif'>%s"
                   "</body></html>") % Markup("").join(body),
            headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/shop/wishlist/diagnose/clear", type="http", auth="user",
                methods=["POST"], website=True, sitemap=False)
    def clear(self, **kwargs):
        """Delete the signed-in administrator's own unreachable rows.

        ONLY THE ONES THE PAGE CANNOT REACH, and only this partner's. A wish
        that is working is left alone, and nobody else's wishlist is touched -
        this exists to undo a stuck row, not to tidy the database.
        """
        if not request.env.user.has_group("base.group_system"):
            raise AccessError(request.env._("Administrators only."))

        Wish = request.env["product.wishlist"].sudo().with_context(
            active_test=False)
        rows = Wish.search(
            [("partner_id", "=", request.env.user.partner_id.id)])
        (rows - request.env["product.wishlist"].current()).unlink()

        return request.redirect("/shop/wishlist/diagnose")
