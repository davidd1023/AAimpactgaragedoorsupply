"""WHAT HIS OWN ORDERS SAY GOES WITH WHAT, SO NOBODY HAS TO TYPE IT IN.

Owner, 2026-10-27: *"could you automate a system that will recommend additional
products the same way that the alternative product thing works. this way i wont
have to individually go into every products page to seach which products i
should recommend alongside it."*

HE ALREADY ANSWERED THE QUESTION, TWELVE HUNDRED TIMES, IN HIS ORDER BOOK.
When he was asked how to pick one cable out of twelve, the honest answer was
that a kit does not know the door height or the drum and no rule written here
could work it out. That is still true. But the question "which cable do people
who buy this kit buy" is not an engineering question at all - it is a counting
question, and the answer is sitting in `sale_order_line`. The shop has been
answering it at the counter all year.

So: for every kit and the custom spring, count the other products that appear
on the SAME order, and keep the ones that come up often enough to be a habit
rather than a coincidence. One row per pair, with the number of orders behind
it, so the page can show the commonest first and the review screen can show
him why.

WHAT THIS IS NOT. It is not a guess about garage doors and it is not a model.
It cannot recommend something nobody has ever bought alongside, which is also
its best property: everything it says, his own shop has done. Where it has
nothing to say the four families still fill the page, exactly as before.

HIS OWN PICK STILL WINS. A product with Alternative Products set ignores all
of this. That was his decision on 2026-10-27 and counting orders does not
overturn it - it only means he no longer has to visit a page to get a sensible
answer out of it.

THREE THINGS THE COUNT HAS TO BE CAREFUL ABOUT, each of which would otherwise
quietly flatter a product:

  * ONE ORDER IS ONE VOTE. Two lines of the same track on one order is one
    customer buying track, not two, so the pairs are counted over DISTINCT
    orders.
  * ONLY ORDERS THAT HAPPENED. A quotation nobody accepted is somebody
    thinking out loud, and a cancelled order is a customer who changed their
    mind. `sale` and `done` only.
  * NOT ITSELF, AND NOT ITS OWN VARIANTS. A track is one product with twenty
    combinations behind it since the catalogue merge, so pairs are counted
    between TEMPLATES - otherwise a kit bought with two lengths of the same
    track would recommend that track twice.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

#: How many orders a pair has to appear on before it is a recommendation.
#: Two, because one is an anecdote - but it is a SETTING, because what counts
#: as a habit depends on how much history there is and that is not a number to
#: need a deploy for.
MIN_ORDERS = 2
MIN_ORDERS_SETTING = "aa_shop_addons.min_orders"

#: How many pairs to keep per product. Well over the eight a family shows, so
#: that the ones filtered out later - unpublished, archived - do not leave a
#: short list.
KEEP = 40


class AaAddonSuggestion(models.Model):
    _name = "aa.addon.suggestion"
    _description = "Add-on bought alongside"
    _order = "product_tmpl_id, orders desc, addon_tmpl_id"
    _rec_name = "addon_tmpl_id"

    product_tmpl_id = fields.Many2one(
        "product.template", string="Shown under", required=True, index=True,
        ondelete="cascade")
    addon_tmpl_id = fields.Many2one(
        "product.template", string="Recommended", required=True, index=True,
        ondelete="cascade")
    orders = fields.Integer(
        string="Orders together", required=True, default=0,
        help="How many of his own orders carried both of these products.")
    computed_on = fields.Datetime(string="Counted on", readonly=True)

    #: `models.Constraint`, not `_sql_constraints` - the old attribute is no
    #: longer supported in Odoo 19 and only warns as it is ignored.
    _pair_is_counted_once = models.Constraint(
        "unique(product_tmpl_id, addon_tmpl_id)",
        "That pair is already counted.",
    )

    # --- who gets recommendations -----------------------------------------

    @api.model
    def _aa_subjects(self):
        """The products a block is drawn under: the kits and the spring.

        Asked for by name - "on every kit and spring page" - and there is no
        point counting pairs for the other fifteen hundred products in the
        catalogue when nothing would ever read them.
        """
        templates = self.env["product.template"].sudo().search([])

        return templates.filtered(lambda t: t._aa_addon_role())

    @api.model
    def _aa_min_orders(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            MIN_ORDERS_SETTING)

        # NOT `int(raw)` ON ITS OWN. An unset parameter reads as False, and
        # `int(False)` is a perfectly good 0 - which clamped to 1 and made
        # every coincidence a recommendation on a database where nobody had
        # ever opened the setting. Caught on the first deploy, in the log line
        # that said "at 1 orders or more".
        if not raw:
            return MIN_ORDERS

        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return MIN_ORDERS

    # --- the counting ------------------------------------------------------

    @api.model
    def _aa_count_pairs(self, subject_ids, minimum):
        """[(product_tmpl_id, addon_tmpl_id, orders)], commonest first.

        SQL rather than the ORM because this is a self-join over every order
        line in the database and reading them into records to count them would
        be a minute's work for a job that takes a moment.
        """
        if not subject_ids:
            return []

        # RAW SQL READS THE DATABASE, NOT THE ORM'S PENDING WRITES. An order
        # confirmed a moment ago may still be sitting in the cache, and this
        # would count the shop as it was before it. Six tests failed on
        # exactly that before the flush was here.
        self.env.flush_all()

        self.env.cr.execute("""
            WITH sold AS (
                SELECT DISTINCT line.order_id, variant.product_tmpl_id AS tmpl
                  FROM sale_order_line line
                  JOIN sale_order ord ON ord.id = line.order_id
                  JOIN product_product variant ON variant.id = line.product_id
                 WHERE ord.state IN ('sale', 'done')
                   AND line.display_type IS NULL
            )
            SELECT subject.tmpl, alongside.tmpl, count(*) AS orders
              FROM sold subject
              JOIN sold alongside
                ON alongside.order_id = subject.order_id
               AND alongside.tmpl <> subject.tmpl
             WHERE subject.tmpl IN %s
             GROUP BY subject.tmpl, alongside.tmpl
            HAVING count(*) >= %s
             ORDER BY subject.tmpl, orders DESC, alongside.tmpl
        """, (tuple(subject_ids), minimum))

        return self.env.cr.fetchall()

    @api.model
    def _aa_sellable(self, template_ids):
        """The ones worth putting on a page, of the ones that were counted.

        A delivery charge and a down payment are on plenty of orders and are
        not add-ons; an unpublished product cannot be reached; the plastic
        filler is deliberately unpublished because it is not sold on its own
        (CLAUDE.md, 2026-10-08) and so is excluded by the same rule.
        """
        if not template_ids:
            return self.env["product.template"]

        return self.env["product.template"].sudo().search([
            ("id", "in", list(template_ids)),
            ("is_published", "=", True),
            ("type", "!=", "service"),
        ])

    # --- rebuilding --------------------------------------------------------

    @api.model
    def _aa_rebuild(self):
        """Count every pair again and replace the table. Returns the count.

        REPLACED RATHER THAN TOPPED UP: a pair that has stopped being bought
        together should stop being recommended, and a table that only ever
        grows would go on recommending last spring's track for ever.
        """
        subjects = self._aa_subjects()
        minimum = self._aa_min_orders()
        pairs = self._aa_count_pairs(subjects.ids, minimum)

        allowed = self._aa_sellable({addon for _s, addon, _n in pairs})
        allowed_ids = set(allowed.ids)
        now = fields.Datetime.now()

        kept = {}

        for subject, addon, orders in pairs:
            if addon not in allowed_ids:
                continue

            for_subject = kept.setdefault(subject, [])

            if len(for_subject) < KEEP:
                for_subject.append((addon, orders))

        rows = [{
            "product_tmpl_id": subject,
            "addon_tmpl_id": addon,
            "orders": orders,
            "computed_on": now,
        } for subject, addons in kept.items() for addon, orders in addons]

        self.sudo().search([]).unlink()
        self.sudo().create(rows)

        _logger.info(
            "aa_shop_addons: %s recommendations over %s products, at %s"
            " orders or more", len(rows), len(kept), minimum)

        return len(rows)

    @api.model
    def _aa_cron_rebuild(self):
        """Nightly. The order book changes every day and nobody should have to
        remember to press a button for the website to keep up."""
        self._aa_rebuild()

    def action_aa_rebuild(self):
        """The button, on the Settings page and over the review list."""
        self.env["aa.addon.suggestion"]._aa_rebuild()

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    # --- what the product page asks ---------------------------------------

    @api.model
    def _aa_for(self, template):
        """The recommended templates for one product, commonest first.

        Read with sudo because the people this is for are shoppers, who have
        no business reading an internal table - and ordered here rather than
        in the caller, because "bought together most often" is the whole point
        and a many2many would have thrown it away.
        """
        rows = self.sudo().search([("product_tmpl_id", "=", template.id)])
        products = self.env["product.template"].sudo().browse(
            [row.addon_tmpl_id.id for row in rows])

        # browse() keeps the order asked for, but a product deleted since the
        # count would be a missing record rather than a missing card.
        return products.exists().filtered(
            lambda product: product.is_published and product.id != template.id)
