"""NOT TWO EMAILS FOR THE SAME ORDER.

Owner, 2026-10-27, having placed order S00070 and received both at 8:15 AM:
*"when making an order i got 2 emails about the invoice ... i need you to make
it so that email is no longer sent"* - the one to stop being "Order S00070 is
confirmed - W/O #228", the one to keep being the invoice.

He is right that they say the same thing. A website order is paid at checkout,
so Odoo confirms it and raises the invoice in the same breath, and the customer
gets a confirmation carrying the quotation PDF and an invoice carrying the
invoice PDF, moments apart, for one $0.54 order.

BUT THE CONFIRMATION IS NOT ONLY A WEBSITE EMAIL. A dealer placing a Quick
Order charged to account gets it too (`aa_dealer_orders/controllers.py`, and
`models.py` for the on-account payment flow), and that order raises NO invoice
at the time - so for a dealer it is the only acknowledgement until the "ready
to collect" email days later. Asked which he wanted, the owner chose to stop it
only where the invoice follows.

So the question this asks is not "is this the website" but **"has this order
already been paid"**, because that is the thing that makes Odoo raise and send
an invoice straight away. A dealer's on-account transaction sits at `pending`
and never becomes `done`, which is exactly the distinction wanted, and a back
office order typed in by hand has no transaction at all and keeps its
confirmation.

THE TEMPLATE IS LEFT IN PLACE. `data/customer_emails.xml` still carries the
wording, still owns the record, and the tests still render it - because the
underlying record is Odoo's own, and abandoning it would not stop anything, it
would just mean Odoo's generic wall of table goes out instead on the paths
that still use it.
"""

from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _aa_paid_online(self):
        """Has a payment gone through for this order already?

        Which is the signal that an invoice is about to be raised and emailed,
        and so that a confirmation email would be the second of two.
        """
        self.ensure_one()

        # Guarded because the field arrives with the payment modules rather
        # than with `sale`, and this module does not depend on them.
        if "transaction_ids" not in self._fields:
            return False

        return bool(self.transaction_ids.filtered(
            lambda tx: tx.state in ("done", "authorized")))

    def _send_order_confirmation_mail(self):
        """Odoo's hook, narrowed to the orders that have nothing else coming.

        Narrowed rather than switched off: `super()` still runs, on the orders
        that should still get it, so anything Odoo or another module does in
        here keeps happening for them.
        """
        keep = self.filtered(lambda order: not order._aa_paid_online())

        return super(SaleOrder, keep)._send_order_confirmation_mail()
