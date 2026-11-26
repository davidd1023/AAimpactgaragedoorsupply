"""JORGE'S TRACK CARD, STRAIGHT TO THE POINT (owner, 2026-11-26).

"necesito que cuando le llegue la tarea a jorge que sea mas simplificado y
directo al grano, deberiamos darle que track deberia coger y a cuanto lo debe
cortar si es el horizontal, ahi mismo darle opcion de escoger otra medida de
horizontal disponible si de ese que necesitamos no hay, importante debe tener
la medida de corte del horizontal y con el vertical lo mismo ... y dejar la
cantidad de jamb bracket que necesita por vertical" - and, the same minute:
"importante si es high lift debe salir, o cualquier tipo de lift".

So each track job on a Track Prep card is drawn as four facts, biggest first:

  * WHAT TO TAKE - the RAW track the job comes off, how many, and how many are
    on the rack (with the Change button beside it: track_swap.py);
  * WHAT TO CUT IT TO - or that it is used as it comes;
  * THE LIFT - Standard, High Lift 24", whatever the order says;
  * for a vertical, THE JAMB BRACKETS PER VERTICAL.

Everything else the old card listed (flag angles, lag screws, the parts
checklist) is still on the order and still comes off stock when the job is
done; it is just not in Jorge's way. A prep note on the part (the ATL
horizontal without its angle) is an instruction, so it stays.

`aa_track_card` is the whole thing as JSON; the card draws it
(track_card.js). Not stored: stock and the RAW component change under it.
"""

import json
import logging
import re

from odoo import fields, models

from .mrp_production import CUSTOM_TRACK, inches_label, qty_label
from .track_swap import inches_text, raw_track_facts

_logger = logging.getLogger(__name__)

JAMB = re.compile(r"jamb\s*bracket", re.I)
JAMB_NUMBER = re.compile(r"#\s*(\d+)")


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    aa_track_card = fields.Text(
        string="Track Prep Card (data)", compute="_compute_aa_track_card",
        help="What Jorge takes, what he cuts it to, the lift and the jamb brackets.")

    def _compute_aa_track_card(self):
        for production in self:
            # ONE BAD JOB MUST NOT TAKE THE SHOP FLOOR DOWN: every card on the
            # board is read in one go (see hardware_card.py, 2026-10-19). A job
            # whose card cannot be worked out falls back to the old rows.
            try:
                card = production._aa_track_card() if production.id else {}
            except Exception:
                _logger.exception("Track card failed for %s", production.name)
                card = {}
            production.aa_track_card = json.dumps(card) if card else False

    def _aa_track_card(self):
        """{kind, track, lift, take, take_qty, on_hand, short, cut, length,
        pairs, jambs, prep, door} for a track job, or {}."""
        self.ensure_one()
        pairs = self.product_qty or 1.0
        facts = self.product_id._aa_track_facts() if self.product_id else None
        if facts:
            kind, size, colour, length = (
                facts["kind"], facts["size"], facts["colour"], facts["length"])
        elif self.aa_station_kind == "track":
            hit = CUSTOM_TRACK.search(self.aa_sale_line_id.name or "")
            if not hit:
                return {}
            size, kind, length, colour = (
                hit.group(1), hit.group(2).lower(), float(hit.group(3)), hit.group(4).strip().title())
        else:
            return {}

        move = self._aa_raw_track_move()
        raw = move.product_id if move else self.env["product.product"]
        raw_facts = raw_track_facts(raw) if raw else None
        pieces = move.product_uom_qty if move else 2.0 * pairs
        # CUT unless the RAW piece is exactly the length: a longer piece (or
        # none chosen yet) is cut down to it.
        cut = not raw_facts or raw_facts["inches"] > length + 0.01
        on_hand = raw.qty_available if raw else 0.0

        card = {
            "kind": kind,
            "track": '%s" %s · %s' % (size, kind.title(), colour),
            "lift": self._aa_track_lift(),
            "take": raw.with_context(display_default_code=False).display_name if raw else "",
            "take_length": inches_text(raw_facts["inches"]) if raw_facts else "",
            "take_qty": qty_label(pieces),
            "on_hand": qty_label(on_hand) if raw else "",
            "short": bool(raw) and on_hand < pieces,
            "cut": cut,
            "length": inches_label(length),
            "pairs": qty_label(pairs),
            "door": "%s'" % facts["door"] if facts and facts.get("door") else "",
            # RAW TRACK IS COUNTED IN PAIRS (owner): a pair is two verticals,
            # LH and RH, so the brackets are shared over pairs x 2.
            "jambs": self._aa_track_jambs(2.0 * pairs) if kind == "vertical" else [],
            "prep": [t.aa_prep_note for t in self.move_raw_ids.product_id.product_tmpl_id
                     if "aa_prep_note" in t._fields and t.aa_prep_note],
        }
        return card

    def _aa_track_jambs(self, pieces):
        """[{name, per}] - jamb brackets per vertical piece, by number."""
        verticals = pieces or 1.0
        jambs = []
        for move in self.move_raw_ids.filtered(
                lambda m: m.state != "cancel" and JAMB.search(m.product_id.name or "")):
            name = move.product_id.with_context(display_default_code=False).display_name
            number = JAMB_NUMBER.search(name)
            jambs.append({
                "name": "#%s" % number.group(1) if number else name,
                "per": qty_label(move.product_uom_qty / verticals),
            })
        return jambs

    def _aa_track_lift(self):
        """The lift of the door(s) this track is for: 'Standard', 'High Lift 24"'...
        or '' when the order never said."""
        self.ensure_one()
        order = self.aa_sale_line_id.order_id
        if not order and self.origin:
            order = self.env["sale.order"].sudo().search([("name", "=", self.origin)], limit=1)
        if not order:
            return ""
        order = order.sudo()
        by_kit, _loose = self._aa_door_split(order)
        if not by_kit:
            return ""
        if self.aa_sale_line_id:
            mine = self.aa_sale_line_id
        else:
            mine = order.order_line.filtered(lambda line: line.product_id == self.product_id)
        kits = [kit for kit, lines in by_kit.items() if lines & mine]
        if not kits and len(by_kit) == 1:
            # One door on the order: whatever track it is, it is for that door.
            kits = list(by_kit)
        lifts = []
        for kit in kits:
            lift = self._aa_card_lift(kit, dict(self._aa_line_notes(kit)), by_kit[kit])
            if lift and lift not in lifts:
                lifts.append(lift)
        return " / ".join(lifts)


class MrpProductionAaWo(models.Model):
    """THE AA IMPACT W/O ON EVERY STATION CARD (owner, 2026-11-26: "que salga
    tambien el AA w/o"). AA Impact types its own work order number into the
    Quick Order's PO field; `_aa_impact_wo` already knows that rule (it fills
    the Overview's AA Impact W/O column), so the card asks the same question."""

    _inherit = "mrp.production"

    aa_impact_wo = fields.Char(string="AA Impact W/O", compute="_compute_aa_impact_wo")

    def _compute_aa_impact_wo(self):
        Workorder = self.env["mrp.workorder"]
        for production in self:
            order = production.aa_sale_line_id.order_id
            if not order and production.origin:
                order = self.env["sale.order"].sudo().search([("name", "=", production.origin)], limit=1)
            production.aa_impact_wo = Workorder._aa_impact_wo(order.sudo()) if order else ""


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    aa_track_card = fields.Text(related="production_id.aa_track_card")
    aa_impact_wo = fields.Char(related="production_id.aa_impact_wo")
