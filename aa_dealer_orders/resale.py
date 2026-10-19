"""TAX-EXEMPT DEALER REGISTRATION, from the dealer's own account page.

The owner, 2026-10-19: the Tax Exempt (Resale Certificate) fiscal position
already exists, but "every dealer has to be set up by hand". So a dealer
uploads their certificate in My Account, somebody here approves or rejects it,
and approval applies the exemption itself.

WHAT APPROVAL GRANTS, and only this: the fiscal position. Ordering on account
is a credit decision - whether you trust somebody to pay later - and it stays a
separate judgement somebody makes by hand (owner's choice, 2026-10-19).

THE EXPIRY DATE IS NOT DECORATION. A lapsed certificate that keeps selling
tax-free is tax the shop owes. The dealer is warned a month out and asked for a
new one; on the day it lapses the exemption comes off and they are charged tax
again until they upload a fresh certificate (owner's choice, 2026-10-19).

THE CERTIFICATE IS NOT PUBLIC. It is somebody's tax document: it is stored as
an attachment on the contact, readable by the shop and by the dealer who
uploaded it, and nowhere else.
"""

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# The position garage_door_supply ships: "Tax Exempt (Resale Certificate)".
EXEMPT_POSITION = "garage_door_supply.fiscal_position_exempt"

# How long before it lapses the dealer is asked for a new one. A month is long
# enough to get a certificate out of an accountant and short enough that the
# date still means something when it arrives.
WARN_DAYS = 30

STATES = [
    ("none", "Not registered"),
    ("pending", "Pending review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("expired", "Expired"),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    aa_resale_state = fields.Selection(
        STATES, string="Resale certificate status", default="none", copy=False,
        tracking=True, index=True,
        help="Where this dealer's tax-exempt registration has got to.")
    aa_resale_certificate = fields.Binary(
        string="Resale certificate", attachment=True, copy=False,
        help="The certificate the dealer uploaded.")
    aa_resale_certificate_name = fields.Char(
        string="Certificate file name", copy=False)
    aa_resale_number = fields.Char(
        string="Certificate number", copy=False,
        help="The number on the certificate, as the dealer typed it.")
    aa_resale_expiry = fields.Date(
        string="Certificate expires", copy=False, tracking=True,
        help="The date on the certificate. The exemption comes off when it "
             "passes.")
    aa_resale_submitted_on = fields.Datetime(
        string="Applied on", copy=False, readonly=True)
    aa_resale_reviewed_on = fields.Datetime(
        string="Reviewed on", copy=False, readonly=True)
    aa_resale_reviewed_by = fields.Many2one(
        "res.users", string="Reviewed by", copy=False, readonly=True)
    aa_resale_note = fields.Char(
        string="Reason", copy=False,
        help="Why it was rejected. The dealer is told this, so it has to be "
             "something they can act on.")
    aa_resale_warned_on = fields.Datetime(
        string="Expiry warning sent", copy=False, readonly=True)

    @api.constrains("aa_resale_expiry", "aa_resale_state")
    def _check_aa_resale_expiry(self):
        for partner in self:
            if partner.aa_resale_state == "pending" and not partner.aa_resale_expiry:
                raise ValidationError(_(
                    "A resale certificate needs the date it expires."))

    # --- the fiscal position -------------------------------------------------

    def _aa_exempt_position(self):
        """The Tax Exempt (Resale Certificate) position, or nothing."""
        return self.env.ref(EXEMPT_POSITION, raise_if_not_found=False)

    def _aa_resale_apply_position(self):
        """Put the exemption on, which is the whole point of approving."""
        position = self._aa_exempt_position()

        if not position:
            raise UserError(_(
                "The Tax Exempt (Resale Certificate) fiscal position is "
                "missing, so there is nothing to apply. Update the Garage Door "
                "Supply module and try again."))

        for partner in self:
            partner.sudo().property_account_position_id = position

    def _aa_resale_clear_position(self):
        """Take it off again - a rejection, or a certificate that has lapsed.

        ONLY OUR OWN POSITION IS REMOVED. A dealer who has been put on some
        other fiscal position by hand keeps it: this came to take the
        exemption off, not to decide what else they should be on.
        """
        position = self._aa_exempt_position()

        for partner in self:
            if position and partner.property_account_position_id == position:
                partner.sudo().property_account_position_id = False

    # --- the dealer's own side ------------------------------------------------

    def _aa_resale_submit(self, certificate, filename, number, expiry):
        """A dealer uploads a certificate. Returns nothing, raises if it cannot.

        RE-APPLYING IS ALLOWED AND NORMAL: a certificate expires every year or
        two, and the same dealer uploads the next one through the same form.
        What they had before is replaced and the state goes back to pending -
        and the EXEMPTION STAYS ON while the new one is reviewed, because a
        dealer who renewed in good time should not be charged tax for the days
        we take to look at it.
        """
        self.ensure_one()

        if not certificate:
            raise UserError(_("Choose the certificate file to upload."))

        if not expiry:
            raise UserError(_("Say when the certificate expires."))

        if fields.Date.to_date(expiry) <= fields.Date.context_today(self):
            raise UserError(_(
                "That certificate expired on %(date)s. Upload one that is "
                "still valid.", date=expiry))

        self.sudo().write({
            "aa_resale_certificate": certificate,
            "aa_resale_certificate_name": filename or "certificate",
            "aa_resale_number": number or False,
            "aa_resale_expiry": expiry,
            "aa_resale_state": "pending",
            "aa_resale_submitted_on": fields.Datetime.now(),
            "aa_resale_reviewed_on": False,
            "aa_resale_reviewed_by": False,
            "aa_resale_note": False,
            "aa_resale_warned_on": False,
        })
        self.sudo().message_post(body=_(
            "Resale certificate uploaded, expiring %(date)s. Waiting to be "
            "approved.", date=expiry))
        self._aa_resale_tell_the_office()

    def _aa_resale_tell_the_office(self):
        """Put the application in front of somebody who can decide it."""
        self.ensure_one()
        group = self.env.ref("sales_team.group_sale_manager",
                             raise_if_not_found=False)

        if not group:
            return

        self.sudo().activity_schedule(
            "mail.mail_activity_data_todo",
            summary=_("Review resale certificate"),
            note=_("%s uploaded a resale certificate. Approve or reject it on "
                   "the contact.", self.display_name),
            # user_ids, not users: Odoo 19 renamed it, the same rename that
            # turned res.users.groups_id into group_ids.
            user_id=(group.user_ids[:1].id or self.env.uid),
        )

    # --- the office's side ----------------------------------------------------

    def action_aa_resale_approve(self):
        """Approve the certificate and apply the exemption."""
        self._aa_resale_check_manager()

        for partner in self:
            if partner.aa_resale_state == "approved":
                raise UserError(_("%s is already approved.",
                                  partner.display_name))

            if not partner.aa_resale_expiry:
                raise UserError(_(
                    "Put the certificate's expiry date on first - the "
                    "exemption comes off when it passes, so it has to have "
                    "one."))

            partner.write({
                "aa_resale_state": "approved",
                "aa_resale_reviewed_on": fields.Datetime.now(),
                "aa_resale_reviewed_by": self.env.uid,
                "aa_resale_note": False,
            })
            partner._aa_resale_apply_position()
            partner.message_post(body=_(
                "Resale certificate approved. Tax exempt until %(date)s.",
                date=partner.aa_resale_expiry))
            partner._aa_resale_email("mail_template_resale_approved")

        return True

    def action_aa_resale_reject(self):
        """Turn it down, with a reason the dealer can act on."""
        self._aa_resale_check_manager()

        for partner in self:
            # A REASON IS NOT OPTIONAL. The dealer is told this and has to know
            # what to do differently; "rejected" on its own starts a phone call
            # that this field would have answered.
            if not (partner.aa_resale_note or "").strip():
                raise UserError(_(
                    "Say why it was rejected in the Reason box first - the "
                    "dealer is told, and they need to know what to fix."))

            partner.write({
                "aa_resale_state": "rejected",
                "aa_resale_reviewed_on": fields.Datetime.now(),
                "aa_resale_reviewed_by": self.env.uid,
            })
            partner._aa_resale_clear_position()
            partner.message_post(body=_(
                "Resale certificate rejected: %s", partner.aa_resale_note))
            partner._aa_resale_email("mail_template_resale_rejected")

        return True

    def _aa_resale_check_manager(self):
        if not self.env.user.has_group("sales_team.group_sale_manager"):
            raise UserError(_(
                "Only a Sales manager can approve or reject a resale "
                "certificate."))

    def _aa_resale_email(self, template_name):
        """Tell the dealer what was decided. They will not sit on the page."""
        self.ensure_one()
        template = self.env.ref(
            "aa_dealer_orders.%s" % template_name, raise_if_not_found=False)

        if template and self.email:
            template.sudo().send_mail(self.id, force_send=True)

    # --- the date doing its job -----------------------------------------------

    @api.model
    def _cron_aa_resale_expiry(self):
        """Warn a month out; take the exemption off on the day.

        BOTH HALVES IN ONE SWEEP, and both safe to run twice: the warning is
        stamped so it goes once, and taking an exemption off a dealer who no
        longer has it is a no-op.
        """
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=WARN_DAYS)

        warning = self.sudo().search([
            ("aa_resale_state", "=", "approved"),
            ("aa_resale_expiry", "!=", False),
            ("aa_resale_expiry", ">=", today),
            ("aa_resale_expiry", "<=", soon),
            ("aa_resale_warned_on", "=", False),
        ])

        for partner in warning:
            try:
                with self.env.cr.savepoint():
                    partner._aa_resale_email("mail_template_resale_expiring")
                    partner.aa_resale_warned_on = fields.Datetime.now()
                    partner.message_post(body=_(
                        "Told them the resale certificate expires %(date)s.",
                        date=partner.aa_resale_expiry))
            except Exception:
                _logger.exception(
                    "aa_dealer_orders: warning %s about their certificate failed",
                    partner.display_name)

        lapsed = self.sudo().search([
            ("aa_resale_state", "=", "approved"),
            ("aa_resale_expiry", "!=", False),
            ("aa_resale_expiry", "<", today),
        ])

        for partner in lapsed:
            partner.aa_resale_state = "expired"
            partner._aa_resale_clear_position()
            partner.message_post(body=_(
                "Resale certificate expired on %(date)s, so the tax exemption "
                "has come off. It goes back on when a new certificate is "
                "uploaded and approved.", date=partner.aa_resale_expiry))

        return len(warning) + len(lapsed)
