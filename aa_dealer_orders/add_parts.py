"""ADMIN ONLY: ADD A HARDWARE BOX, TRACKS OR SPRINGS TO A DEALER ORDER ALREADY PLACED.

Owner, 2026-11-02, about W/O #332 (S00174, PO 1027): *"the original AA Impact
order, our 332, does carry tracks - give me an admin-only button that says
Add Tracks, or if it has no springs Add Springs, and it must show in the
order's cost. Only for AA Impact, the only preferred dealer, charged to
account - on a purchase it must not appear."* Then: *"or box"* - the
hardware box, from the door's measurements, by its series.

#332 had asked for tracks. Its door needs a 144" horizontal and a 124"
vertical 3" track and the longest prepared ones are 132" and 112", so the
Quick Order wrote "AA prepares it" and charged nothing.

Three decisions he made when asked:

- A TRACK LONGER THAN ANY PREPARED ONE IS PRICED PER INCH off the longest
  prepared track of that size and colour (132" at $193.91 -> 144" = $211.54).
- THE BOX is the hardware kit, chosen from the door's width like the Quick
  Order does, with everything its series carries.
- THE ORIGINAL INVOICE IS REDONE, not a second one raised: reset to draft,
  the new lines added, posted again under the same number. Only while nothing
  has been paid on it - a paid invoice cannot be reopened without unpicking
  the payment, so then the extra goes on an invoice of its own.

The buttons open the Quick Order page itself, pre-filled with the order's
doors, rather than a back-office wizard: THE SPRING CALCULATOR ONLY RUNS IN
THE BROWSER (`spring_bridge.js`), so a server-side form could not size a
spring without a second copy of the model, which CLAUDE.md forbids.
"""
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

ADD_PARTS = ('box', 'tracks', 'springs')

_W_RE = re.compile(r'\bW ([\d.]+)"')
_H_RE = re.compile(r'\bH ([\d.]+)"')
_LB_RE = re.compile(r'\|\s*([\d.]+) lb\b')
_TAG_RE = re.compile(r'\bDoor: ([^|\n]+)')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    aa_add_parts_allowed = fields.Boolean(compute='_compute_aa_add_parts')
    aa_needs_box = fields.Boolean(compute='_compute_aa_add_parts')
    aa_needs_tracks = fields.Boolean(compute='_compute_aa_add_parts')
    aa_needs_springs = fields.Boolean(compute='_compute_aa_add_parts')

    # ── who may ─────────────────────────────────────────────────────────────

    def _aa_paid_online(self):
        """A purchase: paid by card at checkout. Charge to Account sits at pending for ever."""
        self.ensure_one()
        return bool(self.sudo().transaction_ids.filtered(lambda t: t.state in ('done', 'authorized')))

    def _aa_can_add_parts(self):
        """Confirmed, for an on-account dealer, not paid at checkout - and asked by an admin."""
        self.ensure_one()
        return bool(
            self.env.user.has_group('base.group_system')
            and self.state == 'sale'
            and self.partner_id._aa_is_on_account_dealer()
            and not self._aa_paid_online()
        )

    # ── what it already carries ─────────────────────────────────────────────

    def _aa_kit_lines(self):
        return self.order_line.filtered(
            lambda l: l.product_id and l.product_uom_qty > 0 and l.product_template_id.aa_dealer_quick_order)

    def _aa_spring_lines(self):
        spring = self.env.ref('spring_engineering.product_custom_spring', raise_if_not_found=False)
        return self.order_line.filtered(
            lambda l: spring and l.product_template_id == spring and l.product_uom_qty > 0)

    def _aa_filler_lines(self):
        filler = self.env.ref('spring_engineering.product_custom_filler', raise_if_not_found=False)
        return self.order_line.filtered(
            lambda l: filler and l.product_template_id == filler and l.product_uom_qty > 0)

    def _aa_track_lines(self):
        custom = self.env.ref('aa_dealer_orders.product_custom_track', raise_if_not_found=False)
        return self.order_line.filtered(
            lambda l: l.product_id and l.product_uom_qty > 0 and (
                (custom and l.product_template_id == custom)
                or l.product_id._aa_track_facts()))

    @api.depends('state', 'partner_id', 'order_line.product_id')
    @api.depends_context('uid')
    def _compute_aa_add_parts(self):
        for order in self:
            allowed = bool(order.id) and order._aa_can_add_parts()
            order.aa_add_parts_allowed = allowed
            order.aa_needs_box = allowed and not order._aa_kit_lines()
            order.aa_needs_tracks = allowed and not order._aa_track_lines()
            order.aa_needs_springs = allowed and not order._aa_spring_lines()

    # ── the doors on it, for the page ───────────────────────────────────────

    def _aa_door_rows(self):
        """The doors this order is for, as the Quick Order page fills a line.

        Off the kit lines first - their track, lift and drum are stored and
        the size and weight are in the line's note. With no kit (the box is
        what is missing), off the spring lines, which store the door as
        numbers. Anything not known is left blank for the admin to type.
        """
        self.ensure_one()
        rows = []
        for line in self._aa_kit_lines():
            text = line.name or ''

            def grab(rx):
                m = rx.search(text)
                return m.group(1).strip() if m else ''

            colour = line.product_id.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_id.name == 'Finish Color')[:1].name or ''
            rows.append({
                'tag': grab(_TAG_RE)[:80],
                'width_in': line.aa_door_width_in or float(grab(_W_RE) or 0),
                'height_in': line.aa_door_height_in or float(grab(_H_RE) or 0),
                'weight': line.aa_door_weight_lb or float(grab(_LB_RE) or 0),
                'qty': int(line.product_uom_qty or 1),
                'track_type': line.aa_track_type or '',
                'lift_type': line.aa_lift_type or 'standard',
                'high_lift': line.aa_high_lift or 0,
                'drum': line.aa_drum or '',
                'color': 'Black' if 'Black' in colour else 'White',
            })
        if rows:
            return rows
        for line in self._aa_spring_lines():
            rows.append({
                'tag': '',
                'width_in': line.aa_door_width_in,
                'height_in': line.aa_door_height_in,
                'weight': line.aa_door_weight_lb,
                'qty': int(line.product_uom_qty or 1),
                'track_type': '',
                'lift_type': 'highlift' if line.aa_door_hi_lift_in else 'standard',
                'high_lift': line.aa_door_hi_lift_in or 0,
                'drum': '',
                'color': '',
            })
        return rows

    # ── the buttons ─────────────────────────────────────────────────────────

    def _aa_open_add_page(self, part, back=''):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/dealer/order/add/{self.id}?part={part}' + (f'&back={back}' if back else ''),
            'target': 'self',
        }

    def action_aa_add_box(self):
        return self._aa_open_add_page('box')

    def action_aa_add_tracks(self):
        return self._aa_open_add_page('tracks')

    def action_aa_add_springs(self):
        return self._aa_open_add_page('springs')

    # ── the invoice ─────────────────────────────────────────────────────────

    def _aa_reinvoice(self, new_lines):
        """Put lines added after invoicing on the bill. Returns a sentence for the chatter.

        Redo the original invoice (owner's choice) while nothing is paid on it;
        otherwise raise an invoice for the new lines alone. An order never
        invoiced is left alone - it is invoiced the way it always would be.
        """
        self.ensure_one()
        invoices = self.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
        if not invoices or not new_lines:
            return ''
        target = invoices.filtered(lambda m: m.state == 'posted' and m.payment_state == 'not_paid').sorted('id')[-1:] \
            or invoices.filtered(lambda m: m.state == 'draft').sorted('id')[-1:]
        if target:
            was_posted = target.state == 'posted'
            try:
                with self.env.cr.savepoint():
                    if was_posted:
                        target.button_draft()
                    sequence = max(target.invoice_line_ids.mapped('sequence') or [10]) + 1
                    vals = []
                    for i, line in enumerate(new_lines):
                        line_vals = line._prepare_invoice_line(sequence=sequence + i)
                        line_vals['quantity'] = line.product_uom_qty
                        vals.append(Command.create(line_vals))
                    target.write({'invoice_line_ids': vals})
                    if was_posted:
                        target.action_post()
                target.message_post(body=_("Lines added to %(so)s by %(user)s were added to this invoice.",
                                           so=self.name, user=self.env.user.name))
                return _("Invoice %s was redone with the new lines.", target.name)
            except Exception as e:  # a lock date, a hash, anything that refuses the reset
                fallback_reason = str(e)
        else:
            fallback_reason = _("the invoice already has a payment on it")
        try:
            with self.env.cr.savepoint():
                moves = self._create_invoices()
                moves.action_post()
        except Exception as e:
            return _("The invoice could not be redone (%(why)s) and no new one could be made (%(err)s) - "
                     "invoice the new lines by hand.", why=fallback_reason, err=str(e))
        return _("A new invoice %(inv)s was made for the new lines (%(why)s).",
                 inv=', '.join(moves.mapped('name')), why=fallback_reason)

    # ── REMOVE A PART (owner, 2026-11-02, on the Shop Floor) ──────────────────
    # "agregar hw box, muelles o tracks aqui en shopfloor si no lo tiene la
    # orden, que por error no se puso o algo, y ademas removerlo de la orden".

    def _aa_part_lines(self, part):
        if part == 'box':
            return self._aa_kit_lines()
        if part == 'tracks':
            return self._aa_track_lines()
        if part == 'springs':
            return self._aa_spring_lines() | self._aa_filler_lines()
        return self.env['sale.order.line']

    def _aa_part_jobs(self, lines):
        """The Shop Floor work behind these lines, whatever its state.

        By the sale line (springs, kits - _aa_create_station_productions writes
        it) and, for a prepared track, by the order's name and the product -
        Odoo's own route raises those and links them by origin only.
        """
        Production = self.env['mrp.production'].sudo()
        jobs = Production.search([('aa_sale_line_id', 'in', lines.ids)]) \
            if 'aa_sale_line_id' in Production._fields else Production.browse()
        tracks = lines.filtered(lambda l: l.product_id._aa_track_facts())
        if tracks and self.name:
            jobs |= Production.search([
                ('origin', '=', self.name),
                ('product_id', 'in', tracks.product_id.ids),
            ])
        return jobs.filtered(lambda p: p.state != 'cancel')

    def aa_remove_part(self, part):
        """Take a hardware box, the tracks or the springs off a placed order.

        Refused once anything has been made or handed over - a job done or
        being worked on, or a delivery already out - because that is not a
        mistake on the order any more, it is a return. Otherwise the jobs are
        cancelled, the lines go to quantity 0 (Odoo keeps a confirmed line, it
        will not delete it) and the unpaid invoice is redone without them.
        """
        self.ensure_one()
        if part not in ADD_PARTS or not self._aa_can_add_parts():
            raise UserError(_("Only an administrator can change a dealer order on account."))
        label = {'box': _('Hardware Box'), 'tracks': _('Tracks'), 'springs': _('Springs')}[part]
        lines = self._aa_part_lines(part)
        if not lines:
            raise UserError(_("%s: there is nothing of that on this order.", label))
        jobs = self._aa_part_jobs(lines)
        started = jobs.filtered(lambda p: p.state == 'done' or p.workorder_ids.filtered(
            lambda w: w.state in ('progress', 'done')))
        if started:
            raise UserError(_("%(label)s cannot be removed: %(jobs)s already started or finished at the station.",
                              label=label, jobs=", ".join(started.mapped('name'))))
        if any(l.qty_delivered for l in lines):
            raise UserError(_("%s cannot be removed: some of it has already been delivered.", label))

        summary = ", ".join(f"{l.product_id.display_name} x{l.product_uom_qty:g} ({l.price_subtotal:.2f})"
                            for l in lines)
        for job in jobs:
            job.action_cancel()
        lines.write({'product_uom_qty': 0})
        invoice_note = self._aa_uninvoice(lines)
        # A kit taken off leaves its boxed lift cables without a job: they get
        # one of their own, exactly as cables bought without a kit do.
        if part == 'box' and hasattr(self, '_aa_create_station_productions'):
            self._aa_create_station_productions()
        if hasattr(jobs, '_aa_tell_the_shop_floor') and jobs:
            jobs._aa_tell_the_shop_floor()
        self.message_post(body=_("%(label)s removed by %(user)s: %(lines)s. %(inv)s",
                                 label=label, user=self.env.user.name, lines=summary, inv=invoice_note))
        return _("%(label)s removed from %(order)s. %(inv)s", label=label,
                 order=self.aa_wo_number or self.name, inv=invoice_note)

    def _aa_uninvoice(self, lines):
        """Take removed lines off the unpaid invoice they were billed on."""
        moves = lines.invoice_lines.move_id.filtered(lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
        notes = []
        for move in moves:
            if move.state == 'posted' and move.payment_state != 'not_paid':
                notes.append(_("Invoice %s already has a payment on it - issue a credit note for the removed lines.",
                               move.name))
                continue
            try:
                with self.env.cr.savepoint():
                    was_posted = move.state == 'posted'
                    if was_posted:
                        move.button_draft()
                    move.invoice_line_ids.filtered(lambda il: il.sale_line_ids & lines).unlink()
                    if was_posted and move.invoice_line_ids:
                        move.action_post()
                notes.append(_("Invoice %s was redone without them.", move.name))
            except Exception as e:
                notes.append(_("Invoice %(inv)s could not be redone (%(err)s) - fix it by hand.",
                               inv=move.name, err=str(e)))
        return " ".join(notes)

    # ── what the Shop Floor shows an admin ──────────────────────────────────

    def _aa_parts_board(self):
        """For the Shop Floor row: which parts this order has, or None when not allowed."""
        self.ensure_one()
        if not self._aa_can_add_parts():
            return None
        return {
            'order_id': self.id,
            'parts': [
                {'part': part, 'label': label, 'has': bool(self._aa_part_lines(part))}
                for part, label in (('box', 'Hardware Box'), ('tracks', 'Tracks'), ('springs', 'Springs'))
            ],
        }
