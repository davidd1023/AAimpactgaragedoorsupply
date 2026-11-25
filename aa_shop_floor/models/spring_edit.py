"""ADMIN: CHANGE A SPRING BEFORE IT GOES TO MICHEL (owner, 2026-11-25).

*"en shop floor necesito hacer algo para que admin antes de mandar los muelles
a michel pueda modificarlos por alguna razon, cambiar cable, id y el drum que
se uso para el calculo y cambiar tipo de lift o cantidad de high lift y esos
muelles si se cambian deben recalcularse y actualizar la orden con su precio"*

THE SIZING STAYS IN THE BROWSER. The calculator is the only spring model and
CLAUDE.md forbids a second one, so the Shop Floor dialog runs it headless -
exactly as the Quick Order page does through `spring_bridge.js` - and posts
the specification it produces. The server then does what it already does for
every spring sold: `quote_assembly` validates and prices it. Nothing here
works out a wire or a length.

WHAT CHANGES, IN ONE GO: the spring line (description, stored spec, door
figures, price), the plastic filler line that goes with a 5 1/4" spring
(added, re-measured or taken to 0), an unpaid invoice (redone; a paid one is
named in the chatter), and the Springs job - its spec, its coil plan and its
card - so Michel winds what the order now says.

REFUSED once the Springs job is being worked on or done: then the steel has
been cut, and changing the order would describe a spring nobody made.
"""
import json

from markupsafe import Markup

from odoo import _, models
from odoo.exceptions import UserError

ID_LABELS = {2.625: '2 5/8"', 3.75: '3 3/4"', 5.25: '5 1/4"'}
# The spec's own first lines, which the quote rewrites; anything else in the
# old note (a dealer's door tag) is kept under the new specification.
QUOTE_PREFIXES = ("Single", "Duplex", "Triplex", "Spring:", "Outer:", "Inner:", "Door:")


def _book(line, target, digits=2):
    """Set price_unit so the line NETS `target` after tax - the same ratio
    correction add_assembly_lines makes, for the same reason."""
    for _i in range(6):
        net = line.price_subtotal
        shortfall = target - net
        if abs(shortfall) < 0.005:
            return
        if net > 0.01:
            candidate = round(line.price_unit * target / net, digits)
        else:
            candidate = round(line.price_unit + shortfall / (line.product_uom_qty or 1), digits)
        if candidate == line.price_unit:
            return
        line.price_unit = candidate


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _aa_spring_edit_board(self):
        """For the Shop Floor row: the springs an admin may still change, or None."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            return None
        rows = []
        for line in self.order_line.filtered(lambda l: l._aa_is_custom_spring()):
            refusal = line._aa_spring_edit_refusal()
            rows.append({
                "line_id": line.id,
                "label": " / ".join((line.aa_spec_note or "").splitlines()[:2])
                or line.product_id.display_name,
                "qty": line.product_uom_qty,
                "price": line.price_subtotal,
                "locked": refusal or "",
                "start": line._aa_spring_edit_start(),
            })
        return rows or None


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _aa_is_custom_spring(self):
        spring = self.env.ref("spring_engineering.product_custom_spring", raise_if_not_found=False)
        return bool(spring and self.product_id.product_tmpl_id == spring
                    and self.product_uom_qty > 0 and self.spring_spec_json)

    def _aa_spring_jobs(self):
        return self.env["mrp.production"].sudo().search([
            ("aa_sale_line_id", "=", self.id), ("state", "!=", "cancel")])

    def _aa_spring_edit_refusal(self):
        """Why this spring cannot be changed any more, or ''."""
        self.ensure_one()
        try:
            spec = json.loads(self.spring_spec_json or "{}")
        except ValueError:
            spec = {}
        if spec.get("assembly") != "Single":
            return _("Only a single spring can be changed here.")
        jobs = self._aa_spring_jobs()
        if jobs.filtered(lambda j: j.state == "done"
                         or j.workorder_ids.filtered(lambda w: w.state in ("progress", "done"))):
            return _("The springs are already being made or done.")
        if self.qty_delivered:
            return _("The springs were already delivered.")
        return ""

    def _aa_spring_edit_start(self):
        """What the dialog opens with: the spring as it was ordered."""
        self.ensure_one()
        spec = json.loads(self.spring_spec_json or "{}")
        item = (spec.get("items") or [{}])[0]
        door = spec.get("door") or {}
        height = self.aa_door_height_in or 0
        return {
            "springs": spec.get("springs") or 2,
            "spring_id": ID_LABELS.get(float(item.get("id") or 0), '2 5/8"'),
            "wire": float(item.get("wire") or 0),
            "length": float(item.get("length") or 0),
            "drum": spec.get("drum") or "",
            "cycles": "{:,}".format(int(door.get("cycles") or 10000)),
            "weight": self.aa_door_weight_lb or door.get("weight") or 0,
            "height_in": height,
            "width_in": self.aa_door_width_in or 0,
            "hi_lift": self.aa_door_hi_lift_in or 0,
            "turns": spec.get("turns") or 0,
        }

    def _aa_spring_quote(self, spec):
        from odoo.addons.spring_engineering.controllers.main import quote_assembly
        quote = quote_assembly(spec)
        if quote.get("error"):
            raise UserError(quote["error"])
        return quote

    def aa_quote_spring(self, spec):
        """The price the spring would have, without changing anything."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an administrator can change a spring."))
        quote = self._aa_spring_quote(spec)
        qty = self.product_uom_qty or 1
        return {
            "total": round(quote["total"] * qty, 2),
            "old_total": round(self.price_subtotal + self._aa_filler_line().price_subtotal, 2),
        }

    def _aa_filler_line(self):
        """The plastic filler that came with this spring (5 1/4" only)."""
        self.ensure_one()
        filler = self.env.ref("spring_engineering.product_custom_filler", raise_if_not_found=False)
        if not filler:
            return self.browse()
        lines = self.order_id.order_line.filtered(
            lambda l: l.product_id.product_tmpl_id == filler and l.product_uom_qty > 0)
        if len(lines) <= 1:
            return lines
        # Several 5 1/4" springs on one order: the one cut to this spring.
        try:
            spec = json.loads(self.spring_spec_json or "{}")
            inches = sum(float(i["length"]) for i in spec.get("items", []) if float(i["id"]) == 5.25)
            feet = round(spec.get("springs", 0) * inches / 12.0 * self.product_uom_qty, 4)
        except (ValueError, KeyError, TypeError):
            return self.browse()
        return lines.filtered(lambda l: abs(l.product_uom_qty - feet) < 0.01)[:1]

    def aa_respec_spring(self, spec):
        """Replace this spring with the one in `spec`, everywhere it is written."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an administrator can change a spring."))
        line = self.sudo()
        if not line._aa_is_custom_spring():
            raise UserError(_("That is not a custom spring line."))
        refusal = line._aa_spring_edit_refusal()
        if refusal:
            raise UserError(refusal)
        quote = line._aa_spring_quote(spec)
        order = line.order_id
        qty = line.product_uom_qty or 1
        old = {"name": line.aa_spec_note or line.name, "total": line.price_subtotal}
        filler = line._aa_filler_line()
        old["total"] += filler.price_subtotal

        # THE SPRING LINE.
        keep = [r for r in (line.aa_spec_note or "").splitlines()
                if r.strip() and not r.strip().startswith(QUOTE_PREFIXES)]
        description = quote["description"] + ("\n" + "\n".join(keep) if keep else "")
        line.aa_write_door(quote.get("door") or {}, note="\n".join(description.splitlines()[1:]).strip())
        line.write({
            "name": description,
            "spring_spec_json": json.dumps(quote["spec"]),
            "price_unit": quote["assembly_total"],
        })
        _book(line, round(quote["assembly_total"] * qty, 2))

        # THE FILLER: added, re-measured or taken to 0 with the spring.
        feet = round(quote["filler_feet"] * qty, 4)
        if feet > 0:
            if not filler:
                product = self.env.ref("spring_engineering.product_custom_filler").sudo().product_variant_id
                filler = self.env["sale.order.line"].sudo().create({
                    "order_id": order.id, "product_id": product.id, "product_uom_qty": feet,
                })
            filler.write({
                "product_uom_qty": feet,
                "name": 'Plastic Filler for 5 1/4" spring\n%s length%s of %s", cut to the spring' % (
                    quote["springs"], "s" if quote["springs"] != 1 else "",
                    round(quote["filler_inches"], 2)),
                "price_unit": quote["filler_unit"],
            })
            _book(filler, round(quote["filler"] * qty, 2), digits=4)
        elif filler:
            filler.product_uom_qty = 0

        invoice_note = line._aa_respec_invoices(line | filler)

        # THE SPRINGS JOB: what Michel winds, and the coil it is cut from.
        for job in line._aa_spring_jobs():
            job.aa_spring_spec_json = line.spring_spec_json
            if hasattr(job, "_aa_replan_coil_cuts"):
                job._aa_replan_coil_cuts()
            if hasattr(job, "_compute_aa_shop_spec"):
                job._compute_aa_shop_spec()
            job.message_post(body=_("Spring changed by %s before winding.", self.env.user.name))

        new_total = line.price_subtotal + (filler.price_subtotal if filler else 0.0)
        body = Markup("<p>%s</p><p><b>%s</b><br/>%s</p><p><b>%s</b><br/>%s</p><p>%s</p>") % (
            _("Spring changed by %(user)s: %(old).2f -> %(new).2f.",
              user=self.env.user.name, old=old["total"], new=new_total),
            _("Before"), Markup("<br/>").join((old["name"] or "").splitlines()),
            _("Now"), Markup("<br/>").join((line.aa_spec_note or "").splitlines()),
            invoice_note,
        )
        order.message_post(body=body)
        return {
            "old_total": round(old["total"], 2),
            "new_total": round(new_total, 2),
            "invoice": invoice_note,
        }

    def _aa_respec_invoices(self, lines):
        """Bring an unpaid invoice into line with the changed spring."""
        lines = lines.filtered("id")
        order = lines.order_id[:1]
        moves = order.invoice_ids.filtered(lambda m: m.move_type == "out_invoice" and m.state != "cancel")
        if not moves:
            return ""
        notes = []
        for move in moves:
            if move.state == "posted" and move.payment_state != "not_paid":
                notes.append(_("Invoice %s already has a payment on it - settle the difference by hand.",
                               move.name))
                continue
            try:
                with self.env.cr.savepoint():
                    was_posted = move.state == "posted"
                    if was_posted:
                        move.button_draft()
                    invoiced = move.invoice_line_ids.filtered(lambda il: il.sale_line_ids & lines)
                    for inv_line in invoiced:
                        sale_line = inv_line.sale_line_ids & lines
                        if not sale_line.product_uom_qty:
                            inv_line.unlink()
                        else:
                            inv_line.write({"quantity": sale_line.product_uom_qty,
                                            "price_unit": sale_line.price_unit,
                                            "name": sale_line.name})
                    missing = lines.filtered(lambda l: l.product_uom_qty and not (l.invoice_lines & move.invoice_line_ids))
                    if missing:
                        start = max(move.invoice_line_ids.mapped("sequence") or [10]) + 1
                        vals = []
                        for i, sale_line in enumerate(missing):
                            values = sale_line._prepare_invoice_line(sequence=start + i)
                            values["quantity"] = sale_line.product_uom_qty
                            vals.append((0, 0, values))
                        move.write({"invoice_line_ids": vals})
                    if was_posted:
                        move.action_post()
                notes.append(_("Invoice %s was redone with the new price.", move.name))
            except Exception as error:  # a lock date, anything that refuses the reset
                notes.append(_("Invoice %(inv)s could not be redone (%(err)s) - fix it by hand.",
                               inv=move.name, err=str(error)))
        return " ".join(notes)
