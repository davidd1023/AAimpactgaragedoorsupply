"""TAX-EXEMPT DEALER REGISTRATION AND APPROVAL.

The owner, 2026-10-19: the Tax Exempt (Resale Certificate) fiscal position
exists, but dealers have no way to register and "every dealer has to be set up
by hand". So: a form where the dealer uploads the certificate, Approve and
Reject for the office, an expiry date, and the exemption applied by the
approval itself.

Three decisions he made when asked: the dealer applies SIGNED IN from My
Account (the certificate attaches to a real account, with no duplicate contacts
to merge); approval grants the tax exemption and NOTHING else, because ordering
on account is a credit decision; and when the date passes the dealer is warned a
month out and then the exemption comes off.
"""

import base64
import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import HttpCase, tagged

# A small real PDF, so the upload path is exercised with something that is
# actually the thing it claims to be.
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@tagged("post_install", "-at_install")
class ResaleCertificateCase(HttpCase):

    PASSWORD = "aa-dealer-password"

    def setUp(self):
        super().setUp()
        self.dealer = self.env["res.users"].create({
            "name": "Hector's Doors",
            "login": "aa_dealer_applicant",
            "email": "hector@example.com",
            "password": self.PASSWORD,
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.partner = self.dealer.partner_id
        self.position = self.env.ref("garage_door_supply.fiscal_position_exempt")
        self.next_year = fields.Date.context_today(self.partner) + timedelta(days=365)

    def _apply(self, expiry=None, partner=None):
        """A certificate uploaded, as the portal form does it."""
        (partner or self.partner)._aa_resale_submit(
            certificate=base64.b64encode(PDF),
            filename="resale.pdf",
            number="RS-12345",
            expiry=expiry or self.next_year,
        )

    @property
    def _exempt(self):
        return self.partner.property_account_position_id == self.position

    # --- the dealer registers -------------------------------------------------

    def test_the_fiscal_position_this_is_all_about_exists(self):
        """Named by its xml id rather than by its wording, which has already
        changed once: the owner calls it "Tax Exempt - Resale Dealer" and the
        record says "Tax Exempt (Resale Certificate)"."""
        self.assertTrue(self.position, "the exempt fiscal position is missing")

    def test_uploading_a_certificate_puts_it_in_the_queue(self):
        self._apply()

        self.assertEqual(self.partner.aa_resale_state, "pending")
        self.assertEqual(self.partner.aa_resale_certificate_name, "resale.pdf")
        self.assertEqual(self.partner.aa_resale_number, "RS-12345")
        self.assertEqual(self.partner.aa_resale_expiry, self.next_year)
        self.assertTrue(self.partner.aa_resale_submitted_on)
        self.assertTrue(base64.b64decode(
            self.partner.aa_resale_certificate).startswith(b"%PDF"))

    def test_applying_does_not_exempt_anybody_by_itself(self):
        """ANYBODY COULD UPLOAD ANYTHING. The exemption waits for a person."""
        self._apply()
        self.assertFalse(self._exempt)

    def test_a_certificate_that_has_already_expired_is_refused(self):
        yesterday = fields.Date.context_today(self.partner) - timedelta(days=1)

        with self.assertRaises(UserError):
            self._apply(expiry=yesterday)

        self.assertEqual(self.partner.aa_resale_state, "none")

    def test_a_pending_application_must_carry_a_date(self):
        with self.assertRaises(ValidationError):
            self.partner.write({"aa_resale_state": "pending",
                                "aa_resale_expiry": False})

    # --- the office decides ---------------------------------------------------

    def test_approving_applies_the_exemption(self):
        """THE WHOLE POINT. "When a dealer is approved, the tax-exempt fiscal
        position is applied automatically"."""
        self._apply()
        self.partner.action_aa_resale_approve()

        self.assertEqual(self.partner.aa_resale_state, "approved")
        self.assertTrue(self._exempt)
        self.assertTrue(self.partner.aa_resale_reviewed_on)
        self.assertEqual(self.partner.aa_resale_reviewed_by, self.env.user)

    def test_approving_grants_the_exemption_and_nothing_else(self):
        """Ordering on account is a credit decision and stays a separate
        judgement (owner's choice, 2026-10-19)."""
        self._apply()
        before = self.partner.aa_order_on_account
        self.partner.action_aa_resale_approve()

        self.assertEqual(self.partner.aa_order_on_account, before)

    def test_the_dealer_is_told_it_was_approved(self):
        self._apply()
        self.partner.action_aa_resale_approve()
        mails = self.env["mail.mail"].search(
            [("model", "=", "res.partner"), ("res_id", "=", self.partner.id)])

        self.assertTrue(mails, "the dealer was not told")
        self.assertIn("approved", (mails[0].subject or "").lower())

    def test_rejecting_will_not_go_without_a_reason(self):
        """The dealer is told what it says, and "rejected" on its own starts a
        phone call that the reason would have answered."""
        self._apply()

        with self.assertRaises(UserError):
            self.partner.action_aa_resale_reject()

        self.assertEqual(self.partner.aa_resale_state, "pending")

    def test_rejecting_with_a_reason_tells_the_dealer_why(self):
        self._apply()
        self.partner.aa_resale_note = "The certificate was not readable."
        self.partner.action_aa_resale_reject()

        self.assertEqual(self.partner.aa_resale_state, "rejected")
        self.assertFalse(self._exempt)
        mails = self.env["mail.mail"].search(
            [("model", "=", "res.partner"), ("res_id", "=", self.partner.id)])
        self.assertIn("not readable", mails[0].body_html or "")

    def test_rejecting_takes_an_exemption_back_off(self):
        """A certificate approved and then found wanting."""
        self._apply()
        self.partner.action_aa_resale_approve()
        self.assertTrue(self._exempt)

        self.partner.aa_resale_note = "Certificate belongs to another business."
        self.partner.action_aa_resale_reject()

        self.assertFalse(self._exempt)

    def test_only_a_sales_manager_decides(self):
        self._apply()
        clerk = self.env["res.users"].create({
            "name": "A clerk", "login": "aa_resale_clerk",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("sales_team.group_sale_salesman").id])]})

        with self.assertRaises(UserError):
            self.partner.with_user(clerk).action_aa_resale_approve()

        self.assertFalse(self._exempt)

    def test_approving_without_a_date_is_refused(self):
        """The exemption comes off when the date passes, so it has to have
        one - a certificate with no end never ends."""
        self.partner.write({"aa_resale_state": "rejected",
                            "aa_resale_expiry": False})

        with self.assertRaises(UserError):
            self.partner.action_aa_resale_approve()

    # --- the date doing its job -----------------------------------------------

    def _sweep(self):
        return self.env["res.partner"]._cron_aa_resale_expiry()

    def test_a_certificate_about_to_lapse_warns_the_dealer(self):
        self._apply(expiry=fields.Date.context_today(self.partner)
                    + timedelta(days=10))
        self.partner.action_aa_resale_approve()
        self.env["mail.mail"].search([("model", "=", "res.partner")]).unlink()

        self._sweep()

        self.assertTrue(self.partner.aa_resale_warned_on)
        mails = self.env["mail.mail"].search(
            [("model", "=", "res.partner"), ("res_id", "=", self.partner.id)])
        self.assertIn("expires soon", (mails[0].subject or "").lower())
        self.assertTrue(self._exempt, "warning is not expiring")

    def test_the_warning_goes_once(self):
        self._apply(expiry=fields.Date.context_today(self.partner)
                    + timedelta(days=10))
        self.partner.action_aa_resale_approve()
        self._sweep()
        self.env["mail.mail"].search([("model", "=", "res.partner")]).unlink()
        self._sweep()

        self.assertFalse(self.env["mail.mail"].search(
            [("model", "=", "res.partner"), ("res_id", "=", self.partner.id)]),
            "it warned them twice")

    def test_a_certificate_with_time_left_is_not_warned_about(self):
        self._apply()
        self.partner.action_aa_resale_approve()
        self._sweep()

        self.assertFalse(self.partner.aa_resale_warned_on)

    def test_the_exemption_comes_off_when_the_date_passes(self):
        """A LAPSED CERTIFICATE THAT KEEPS SELLING TAX-FREE IS TAX THE SHOP
        OWES (owner's choice, 2026-10-19)."""
        self._apply()
        self.partner.action_aa_resale_approve()
        self.assertTrue(self._exempt)

        # The date passes.
        self.partner.aa_resale_expiry = \
            fields.Date.context_today(self.partner) - timedelta(days=1)
        self._sweep()

        self.assertEqual(self.partner.aa_resale_state, "expired")
        self.assertFalse(self._exempt)

    def test_expiring_is_safe_to_run_twice(self):
        self._apply()
        self.partner.action_aa_resale_approve()
        self.partner.aa_resale_expiry = \
            fields.Date.context_today(self.partner) - timedelta(days=1)
        self._sweep()
        self._sweep()

        self.assertEqual(self.partner.aa_resale_state, "expired")

    def test_a_dealer_put_on_another_position_by_hand_keeps_it(self):
        """THIS CAME TO TAKE THE EXEMPTION OFF, not to decide what else
        somebody should be on."""
        other = self.env["account.fiscal.position"].search(
            [("id", "!=", self.position.id)], limit=1)
        self.assertTrue(other, "no second fiscal position to test with")
        self._apply()
        self.partner.action_aa_resale_approve()
        self.partner.property_account_position_id = other

        self.partner.aa_resale_expiry = \
            fields.Date.context_today(self.partner) - timedelta(days=1)
        self._sweep()

        self.assertEqual(self.partner.property_account_position_id, other)

    def test_renewing_keeps_the_exemption_while_it_is_reviewed(self):
        """A dealer who renewed in good time should not be charged tax for the
        days we take to look at it."""
        self._apply()
        self.partner.action_aa_resale_approve()
        self._apply(expiry=fields.Date.context_today(self.partner)
                    + timedelta(days=730))

        self.assertEqual(self.partner.aa_resale_state, "pending")
        self.assertTrue(self._exempt, "tax came back on while we reviewed it")

    # --- the page the dealer uses ---------------------------------------------

    def test_the_page_offers_the_form(self):
        self.authenticate("aa_dealer_applicant", self.PASSWORD)
        page = self.url_open("/my/resale-certificate").text

        self.assertIn("Tax-exempt dealer status", page)
        self.assertIn('name="certificate"', page)
        self.assertIn('name="expiry"', page)

    def test_the_page_says_where_it_stands(self):
        self._apply()
        self.partner.action_aa_resale_approve()
        self.authenticate("aa_dealer_applicant", self.PASSWORD)
        page = self.url_open("/my/resale-certificate").text

        self.assertIn("Approved", page)
        self.assertIn("not charged sales tax", page)

    def _post_certificate(self, filename, content, expiry=None):
        """Upload through the real form, token and all.

        THROUGH THE ROUTE RATHER THAN THE METHOD, because the method cannot be
        called outside a request at all - the translation of its own error
        message needs one - and because what matters is what the form does with
        a file, not what a function does with a stub.
        """
        self.authenticate("aa_dealer_applicant", self.PASSWORD)
        page = self.url_open("/my/resale-certificate").text
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)

        return self.url_open(
            "/my/resale-certificate",
            data={"csrf_token": token, "number": "RS-1",
                  "expiry": str(expiry or self.next_year)},
            files={"certificate": (filename, content)})

    def test_uploading_something_that_is_not_a_certificate_is_refused(self):
        """A tax document is a PDF or a photograph of one. Anything else is a
        mistake or an attempt, and both are refused the same way."""
        response = self._post_certificate("payload.exe", b"MZ...")

        self.assertEqual(response.status_code, 200)
        self.assertIn("PDF or a photograph", response.text)
        self.assertEqual(self.partner.aa_resale_state, "none",
                         "it was accepted")

    def test_a_certificate_too_big_to_be_one_is_refused(self):
        response = self._post_certificate("huge.pdf", b"%PDF" + b"x" * (9 * 1024 * 1024))

        self.assertIn("bigger than 8 MB", response.text)
        self.assertEqual(self.partner.aa_resale_state, "none")

    def test_a_real_certificate_goes_through_the_form(self):
        """The whole way: the form, the file, the queue."""
        response = self._post_certificate("resale.pdf", PDF)

        self.assertEqual(response.status_code, 200)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.aa_resale_state, "pending")
        self.assertEqual(self.partner.aa_resale_certificate_name, "resale.pdf")
        # Matched on one line of it: the template wraps the sentence, so
        # asserting across the line break asserts the indentation.
        self.assertIn("Your certificate is with us", response.text)

    def test_another_dealer_cannot_see_this_one_s_certificate(self):
        """It is somebody's tax document."""
        self._apply()
        other = self.env["res.users"].create({
            "name": "Someone else", "login": "aa_other_dealer",
            "password": self.PASSWORD,
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])]})
        self.authenticate("aa_other_dealer", self.PASSWORD)
        page = self.url_open("/my/resale-certificate").text

        self.assertNotIn("RS-12345", page)
        self.assertNotIn("resale.pdf", page)
