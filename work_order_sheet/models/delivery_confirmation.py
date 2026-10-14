import uuid

from markupsafe import Markup

from odoo import api, fields, models


def _token(record=None):
    """A confirmation link's secret, long enough that it cannot be guessed."""
    return uuid.uuid4().hex + uuid.uuid4().hex


class StockMove(models.Model):
    _inherit = "stock.move"

    # TICKED BY THE CUSTOMER, on the form, one line at a time. Kept on the move
    # rather than in a list of its own because the move IS the line: what was
    # sent, how many, and now whether it arrived.
    dispatch_received = fields.Boolean(
        string="Confirmed by the customer", copy=False, readonly=True)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # --- the customer's delivery confirmation ---------------------------------
    #
    # A DELIVERY NOTE THAT SIGNS ITSELF BACK. Dispatch finishes an order and it
    # goes out; what comes back is a piece of paper nobody can find, or
    # nothing at all. This is the same thing done once: a link the customer
    # opens on their phone at the kerb, a tick against each item they are
    # handed, and a signature at the bottom.
    #
    # TWO DATES, BOTH ASKED FOR. When the form was made - which is when the
    # delivery was confirmed and the order became ready to go out - and when
    # it was signed. The gap between them is the only honest answer to "when
    # did they actually get it".

    dispatch_access_token = fields.Char(
        string="Confirmation link secret", copy=False, index=True,
        groups="stock.group_stock_user,mrp.group_mrp_user")
    dispatch_form_date = fields.Datetime(
        string="Form made", copy=False, readonly=True)
    dispatch_signed_on = fields.Datetime(
        string="Signed", copy=False, readonly=True)
    dispatch_signed_by = fields.Char(
        string="Signed by", copy=False, readonly=True)
    dispatch_signature = fields.Binary(
        string="Signature", copy=False, readonly=True, attachment=True)
    # The link carries the secret, so it is kept from anybody the secret is
    # kept from - a lesson already learnt on the bench kiosks.
    dispatch_url = fields.Char(
        string="Confirmation form", compute="_compute_dispatch_url",
        groups="stock.group_stock_user,mrp.group_mrp_user")
    # Words, not a boolean: a badge cannot render a boolean, and an order with
    # no form has nothing to say rather than something to worry about.
    dispatch_state = fields.Selection(
        [("open", "Not signed"), ("signed", "Signed")],
        string="Receipt", compute="_compute_dispatch_state", store=True)

    @api.depends("dispatch_access_token")
    def _compute_dispatch_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        for picking in self:
            # sudo for its own read: whoever may read the link may read the
            # token - the same groups - but the compute also runs on behalf of
            # whatever triggered it.
            token = picking.sudo().dispatch_access_token
            picking.dispatch_url = "%s/delivery/%s" % (
                (base or "").rstrip("/"), token) if token else ""

    @api.depends("dispatch_access_token", "dispatch_signed_on")
    def _compute_dispatch_state(self):
        for picking in self:
            if not picking.sudo().dispatch_access_token:
                picking.dispatch_state = False
            else:
                picking.dispatch_state = (
                    "signed" if picking.dispatch_signed_on else "open")

    def _dispatch_form_wanted(self):
        """Is this a transfer a customer signs for?

        THE ONES THAT LEAVE THE BUILDING. An internal move between two of our
        own locations has no customer at the other end, and a receipt from a
        supplier is their paperwork, not ours.
        """
        self.ensure_one()

        return self.picking_type_id.code == "outgoing"

    def _dispatch_form_open(self):
        """Make the form if this transfer should have one. Returns it or none."""
        made = self.browse()

        for picking in self:
            if picking.dispatch_access_token or not picking._dispatch_form_wanted():
                continue

            picking.write({
                "dispatch_access_token": _token(),
                "dispatch_form_date": fields.Datetime.now(),
            })
            made |= picking

        return made

    def action_dispatch_form(self):
        """Make the confirmation form by hand, for a delivery that has none."""
        self._dispatch_form_open()

        return True

    def action_confirm(self):
        """A delivery gets its confirmation form as soon as it is real.

        MADE UP FRONT, NOT ON DEMAND, because the link has to be ON the order
        when somebody goes looking for it - a form that exists only after
        somebody presses a button is a form the driver cannot find at the kerb.
        """
        result = super().action_confirm()
        self._dispatch_form_open()

        return result

    def _dispatch_lines(self):
        """What the customer is being asked to confirm, in printed order."""
        self.ensure_one()

        return self.move_ids.filtered(
            lambda move: move.state != "cancel" and move.product_id
        ).sorted(lambda move: (move.product_id.display_name or "", move.id))

    def _dispatch_log_signature(self, confirmed, missing):
        """Write the receipt into the order's own log.

        THE ORDER IS WHERE PEOPLE LOOK, and a signature that lives only on a
        web page is a signature nobody in the office knows about. Anything the
        customer did NOT tick is named, because that is the line somebody has
        to deal with tomorrow.
        """
        self.ensure_one()
        rows = Markup("").join(
            Markup("<li>%s</li>") % (
                "%g x %s" % (move.product_uom_qty,
                             move.product_id.display_name or ""))
            for move in confirmed
        )
        body = Markup("<p>%s</p><ul>%s</ul>") % (
            self.env._(
                "Delivery confirmed and signed by %(name)s.",
                name=self.dispatch_signed_by or ""),
            rows,
        )

        if missing:
            body += Markup("<p><b>%s</b></p><ul>%s</ul>") % (
                self.env._("Not confirmed by the customer:"),
                Markup("").join(
                    Markup("<li>%s</li>") % (
                        "%g x %s" % (move.product_uom_qty,
                                     move.product_id.display_name or ""))
                    for move in missing
                ),
            )

        self.message_post(body=body, subtype_xmlid="mail.mt_note")

    def _dispatch_groups(self):
        """[(heading, moves)] - the delivery split the way the floor splits it.

        THE SAME FOUR GROUPS THE SHEET PRINTS, and for a different reason. On
        the sheet they decide who makes a thing; here they decide how many
        boxes a customer has to tick. Somebody handed eleven lengths of track
        should be able to say so once.

        A spring is recognised from its order line rather than its name, the
        way the sheet does it, so a configured assembly groups with the
        springs instead of falling into the hardware at the bottom.
        """
        self.ensure_one()
        groups = {}

        for move in self._dispatch_lines():
            name = move.product_id.display_name or ""
            kind = ("spring" if self._work_order_spring(move)
                    else self._work_order_kind(name))
            category, _source = self._work_order_category(move.product_id)
            page = self._work_order_page(kind, category)
            groups.setdefault(page, self.env["stock.move"])
            groups[page] |= move

        return [(page, groups[page]) for page in self.PAGES if groups.get(page)]

    def _dispatch_date(self, value):
        """A moment on the SHOP'S clock, named so nobody has to guess.

        NOT THE READER'S CLOCK, which is the obvious choice and the wrong one
        here. A customer opening this link is not logged in, so Odoo has no
        timezone for them and falls back to UTC - the form would have told a
        customer in Florida that their delivery was signed for at 19:32 when
        it was half past three in the afternoon. And the office, reading the
        same two dates in Odoo, would have seen different numbers again.
        One clock, the company's, with its name printed beside it.
        """
        if not value:
            return ""

        # NOT THE READER'S TIMEZONE EITHER WAY. Falling back to whoever is
        # looking puts the office and the customer on different clocks for the
        # same delivery, which is the whole fault being fixed; a company with
        # no timezone set gets UTC, and the name beside the time says so.
        zone = self.company_id.partner_id.tz or "UTC"

        return fields.Datetime.context_timestamp(
            self.with_context(tz=zone), value).strftime("%d %b %Y %H:%M %Z")
