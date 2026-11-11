"""CUT IT FROM A LONGER RAW TRACK (owner, 2026-11-11).

"si no tenemos un track de cierta medida y usamos otro mas grande, para que el
sistema sepa descontar, le daremos la opcion a Jorge de cambiar el track que
debe coger por el que tenemos en inventario" - and, asked: same size, same
kind (a 3" job takes a 3", a vertical a vertical), LONGER, from stock; Jorge
does it himself from his Track Prep card; THE LEFTOVER IS DISCARDED for now.

So the swap replaces the job's RAW track component with the longer one, and
that is what comes off the shelf when the job is done. Discarding the offcut
needs no code: the whole longer piece is consumed.

THE COLOUR STAYS THE COLOUR. He named size and kind; a black job cut from a
white RAW track is a different track, not a longer one.

A STOCK LENGTH IS REPLACED; A CUSTOM LENGTH IS GIVEN ONE. A prepared track's
job already consumes a RAW piece (its BoM), and the swap points it at a longer
one. A custom-length job (aa_station_kind "track") consumes nothing until
somebody says what it is cut from, so the same button adds the RAW piece -
the cut length is the shortest that will do.
"""

import re

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError

from .mrp_production import CUSTOM_TRACK

# 3" Vertical Track RAW - 7'4" Black   /   2" Horizontal Track RAW - 9'6" White
RAW_TRACK = re.compile(
    r"^\s*(\d)\"\s*(Vertical|Horizontal)\s+Track\s+RAW\s*-\s*(\d+)'\s*(?:(\d+)\")?\s*(\w+)\s*$", re.I)


def raw_track_facts(product):
    """{size, kind, inches, colour} of a RAW track product, or None."""
    hit = RAW_TRACK.match(product.with_context(display_default_code=False).name or "")
    if not hit:
        return None
    return {
        "size": hit.group(1),
        "kind": hit.group(2).lower(),
        "inches": int(hit.group(3)) * 12 + int(hit.group(4) or 0),
        "colour": hit.group(5).title(),
    }


def inches_text(inches):
    feet, rest = divmod(int(inches), 12)
    return "%d'%d\"" % (feet, rest) if rest else "%d'" % feet


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # NOT STORED: stock moves every minute and the card should follow it.
    aa_track_swappable = fields.Boolean(
        string="Track Can Be Changed", compute="_compute_aa_track_swappable",
        help="An open Track Prep job whose RAW track can be swapped for a longer one.")

    def _compute_aa_track_swappable(self):
        for production in self:
            production.aa_track_swappable = bool(production.id) and production.aa_track_swap_allowed()

    def aa_track_swap_board(self):
        """Every job on one card - a merged Track Prep card carries several -
        with what each is cut from and what it could be cut from."""
        board = []
        for production in self:
            if not production.aa_track_swap_allowed():
                continue
            entry = production.aa_track_swap_options()
            entry["production_id"] = production.id
            entry["job"] = production.product_id.with_context(display_default_code=False).display_name
            board.append(entry)
        return board

    # --- what the job is cut from -------------------------------------------

    def _aa_raw_track_move(self):
        """The job's open RAW track component, or an empty recordset."""
        self.ensure_one()
        return self.move_raw_ids.filtered(
            lambda m: m.state not in ("done", "cancel") and raw_track_facts(m.product_id))[:1]

    def _aa_track_need(self):
        """What a RAW piece must match for this job: {size, kind, colour, min_inches,
        current (product or empty)} - or None when this is not a track job."""
        self.ensure_one()
        move = self._aa_raw_track_move()
        if move:
            facts = raw_track_facts(move.product_id)
            # LONGER than what it was going to use: the same length is no swap.
            return dict(facts, min_inches=facts["inches"] + 1, current=move.product_id)
        if self.aa_station_kind == "track" and self.aa_sale_line_id:
            hit = CUSTOM_TRACK.search(self.aa_sale_line_id.name or "")
            if hit:
                return {
                    "size": hit.group(1),
                    "kind": hit.group(2).lower(),
                    "colour": hit.group(4).strip().title(),
                    # A custom piece is cut to its length: the RAW must be at least that.
                    "min_inches": float(hit.group(3)),
                    "current": self.env["product.product"],
                }
        return None

    def _aa_track_pieces(self):
        """How many RAW pieces the job consumes: a stock job keeps its count;
        a custom job cuts LH + RH for every pair."""
        self.ensure_one()
        move = self._aa_raw_track_move()
        return move.product_uom_qty if move else 2.0 * (self.product_qty or 1.0)

    def aa_track_swap_allowed(self):
        """Whether the card shows the button: an open track job with something to swap."""
        self.ensure_one()
        return self.state not in ("done", "cancel") and bool(self._aa_track_need())

    def aa_track_swap_options(self):
        """For the card's dialog: what it is cut from now, and what it could be cut from."""
        self.ensure_one()
        need = self._aa_track_need()
        if not need or self.state in ("done", "cancel"):
            return {"current": False, "options": [], "reason": _("This job has no RAW track to change.")}
        Product = self.env["product.product"]
        candidates = Product.search([
            ("name", "ilike", 'Track RAW'),
            ("type", "=", "consu"),
        ])
        options = []
        for product in candidates:
            facts = raw_track_facts(product)
            if not facts or facts["size"] != need["size"] or facts["kind"] != need["kind"] \
                    or facts["colour"] != need["colour"] or facts["inches"] < need["min_inches"]:
                continue
            if product.qty_available <= 0:
                continue
            options.append({
                "id": product.id,
                "name": product.with_context(display_default_code=False).display_name,
                "length": inches_text(facts["inches"]),
                "inches": facts["inches"],
                "on_hand": product.qty_available,
            })
        options.sort(key=lambda o: o["inches"])
        current = need["current"]
        return {
            "needs": self._aa_track_pieces(),
            "current": current.with_context(display_default_code=False).display_name if current else False,
            "track": '%s" %s · %s' % (need["size"], need["kind"].title(), need["colour"]),
            "options": options,
            "reason": "" if options else _(
                'No longer %(size)s" %(kind)s %(colour)s RAW track is in stock.',
                size=need["size"], kind=need["kind"], colour=need["colour"]),
        }

    def aa_track_swap(self, product_id):
        """Cut this job from `product_id`: replace (or add) its RAW track component."""
        self.ensure_one()
        if self.state in ("done", "cancel"):
            raise UserError(_("%s is already closed; its track cannot be changed.", self.name))
        need = self._aa_track_need()
        new = self.env["product.product"].browse(int(product_id)).exists()
        facts = raw_track_facts(new) if new else None
        # THE SERVER CHECKS AGAIN: the dialog only offered good choices, but a
        # request can be posted by hand.
        if not need or not facts or facts["size"] != need["size"] or facts["kind"] != need["kind"] \
                or facts["colour"] != need["colour"] or facts["inches"] < need["min_inches"]:
            raise UserError(_("That RAW track does not fit this job."))
        old_move = self._aa_raw_track_move()
        qty = self._aa_track_pieces()
        if old_move:
            old_name = old_move.product_id.with_context(display_default_code=False).display_name
            old_move._do_unreserve()
            old_move._action_cancel()
        else:
            old_name = False
        # ODOO'S OWN COMPONENT VALUES, so the new line is the same kind of
        # move as one the BoM made - same locations, references and grouping.
        values = self._get_move_raw_values(
            new, qty, new.uom_id, operation_id=old_move.operation_id.id if old_move else False)
        new_move = self.env["stock.move"].create(values)
        new_move._action_confirm()
        new_move._action_assign()

        new_name = new.with_context(display_default_code=False).display_name
        who = self.env.user.employee_id.name or self.env.user.name
        if old_name:
            body = _("%(who)s cut this from %(new)s x%(qty)s instead of %(old)s (no %(old)s in stock). "
                     "The leftover is discarded.", who=who, new=new_name, old=old_name, qty="%g" % qty)
        else:
            body = _("%(who)s cut this custom-length track from %(new)s x%(qty)s. "
                     "The leftover is discarded.", who=who, new=new_name, qty="%g" % qty)
        self.message_post(body=body)
        order = self.aa_sale_line_id.order_id or self.env["sale.order"].sudo().search(
            [("name", "=", self.origin)], limit=1)
        if order:
            order.sudo().message_post(body=Markup("%s: %s") % (escape(self.name), escape(body)))
        self.invalidate_recordset(["aa_shop_spec"])
        return {"track": new_name}


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_track_swappable = fields.Boolean(related="production_id.aa_track_swappable")
