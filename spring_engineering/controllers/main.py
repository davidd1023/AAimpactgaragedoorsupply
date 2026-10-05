# The calculator on the public website.
#
# WHY A CONTROLLER AT ALL. The module started as a backend app: an
# ir.actions.client plus a menu item, with its assets in web.assets_backend.
# That is reachable only at /odoo/action-..., which IS the backend, so a link
# to it from the website dropped the visitor out of the site and into Odoo.
# There was no frontend route to land on.
from odoo import http
from odoo.http import request


# The one real URL. Everything else redirects here, so links, search engines
# and anybody typing it out land on a single canonical address.
CANONICAL = "/spring-calculator"

# WHAT PEOPLE ACTUALLY TYPE. The route is matched exactly - lowercase, hyphen -
# so /spring_calculator, /Spring-Calculator and /spring-engineering were all a
# 404, which is an unhelpful thing to hand someone who is one underscore out.
# A 301 rather than serving the page at several URLs: the content has one
# address, and the alias tells the browser and the crawler so.
ALIASES = [
    "/spring_calculator",
    "/spring-engineering",
    "/spring_engineering",
    "/springcalculator",
    "/spring-springs",
    "/torsion-calculator",
]


class SpringEngineeringWebsite(http.Controller):
    # auth="public" so a visitor needs no account, website=True so the request
    # carries the site's theme, menus and language, and sitemap=True so the
    # page is offered to search engines like any other.
    @http.route(
        CANONICAL,
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def spring_calculator(self, **kwargs):
        return http.request.render("spring_engineering.calculator_page", {})

    # sitemap=False so only the canonical URL is offered to crawlers.
    @http.route(ALIASES, type="http", auth="public", website=True, sitemap=False)
    def spring_calculator_aliases(self, **kwargs):
        return request.redirect(CANONICAL, code=301)
