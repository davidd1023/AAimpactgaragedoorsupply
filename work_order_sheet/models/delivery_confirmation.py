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
        """Every move the customer is being handed, cancelled ones aside."""
        self.ensure_one()

        return self.move_ids.filtered(
            lambda move: move.state != "cancel" and move.product_id
        ).sorted(lambda move: (move.product_id.display_name or "", move.id))

    def _dispatch_items(self):
        """One row per THING HANDED OVER, which is not one row per move.

        A CABLE IS ONE THING. It leaves the shop as a reel, an oval sleeve, a
        thimble and a stop - four moves against one line on the order - and a
        customer handed one made-up cable should be asked about one made-up
        cable. Asking them to tick a thimble is asking them to reassemble a
        bill of materials on the kerb to work out what they were given.

        THE SHEET'S OWN RULE, not a second one: _work_order_collapses already
        decides when a group of moves is one thing bought and when it is a set
        of parts somebody has to pick, and a hardware kit is deliberately the
        second. The customer's list and the floor's list therefore say the same
        thing about the same delivery.
        """
        self.ensure_one()
        items = []

        for group in self._work_order_groups():
            moves = [move for move in group
                     if move.state != "cancel" and move.product_id]

            if not moves:
                continue

            sale_line = moves[0].sale_line_id

            if self._work_order_collapses(sale_line, moves):
                items.append(self._dispatch_item(
                    sale_line.product_id, sale_line.product_uom_qty,
                    sale_line.product_uom_id.name
                    if "product_uom_id" in sale_line._fields else "",
                    moves))
                continue

            for move in moves:
                items.append(self._dispatch_item(
                    move.product_id, move.product_uom_qty,
                    move.product_uom.name, [move]))

        return sorted(items, key=lambda item: item["name"])

    def _dispatch_item(self, product, quantity, uom, moves):
        """One row of the customer's list, and the moves behind it."""
        records = self.env["stock.move"].browse([move.id for move in moves])

        return {
            # The row is ticked as one, so it is named for one of its moves and
            # answered for all of them.
            "key": records[0].id,
            "name": product.display_name or "",
            "quantity": quantity,
            "uom": uom or "",
            "moves": records,
            "received": all(move.dispatch_received for move in records),
        }

    def _dispatch_log_signature(self, confirmed, missing):
        """`confirmed` and `missing` are rows of _dispatch_items, not moves."""
        """Write the receipt into the order's own log.

        THE ORDER IS WHERE PEOPLE LOOK, and a signature that lives only on a
        web page is a signature nobody in the office knows about. Anything the
        customer did NOT tick is named, because that is the line somebody has
        to deal with tomorrow.
        """
        self.ensure_one()
        rows = Markup("").join(
            Markup("<li>%s</li>") % ("%g x %s" % (item["quantity"], item["name"]))
            for item in confirmed
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
                        "%g x %s" % (item["quantity"], item["name"]))
                    for item in missing
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

        for item in self._dispatch_items():
            move = item["moves"][0]
            kind = ("spring" if self._work_order_spring(move)
                    else self._work_order_kind(item["name"]))

            # A SUMMARISED GROUP TAKES ITS KIND FROM WHAT IT IS MADE OF, the
            # same way the sheet does: a made-up cable may be named for the
            # track it suits, while a GAC reel and a thimble say plainly what
            # they are.
            if not kind and len(item["moves"]) > 1:
                for part in item["moves"]:
                    found = self._work_order_kind(
                        part.product_id.display_name or "")

                    if found:
                        kind = found
                        break

            category, _source = self._work_order_category(move.product_id)
            groups.setdefault(self._work_order_page(kind, category), []).append(
                item)

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
