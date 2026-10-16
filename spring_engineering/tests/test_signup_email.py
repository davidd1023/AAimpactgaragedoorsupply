import re

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessDenied, UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

@tagged("post_install", "-at_install")
class TestConfirmingTheAddress(TransactionCase):
    """An account is not an account until the address behind it answers."""

    def setUp(self):
        super().setUp()
        self.user = self.env["res.users"].create({
            "name": "Unconfirmed Customer", "login": "unconfirmed@example.com",
            "password": "s3cret!",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])]})

    def _credentials(self, password="s3cret!"):
        return {"type": "password", "password": password}

    def _as_them(self):
        """Odoo checks the password of env.user, not of the recordset, so a
        test that calls this as the administrator is only ever asking
        whether the ADMIN's password is "s3cret!"."""
        return self.user.with_user(self.user)

    # --- who has to confirm --------------------------------------------------

    def test_an_account_that_already_existed_is_confirmed(self):
        """THE GRANDFATHER RULE. The column's default fills every row that
        was already there, so nobody loses an account they have been using."""
        self.assertTrue(self.user.aa_email_verified)
        self.assertTrue(self.env.ref("base.user_admin").aa_email_verified)

    def test_starting_verification_clears_the_flag_and_mints_a_link(self):
        self.user._aa_start_email_verification()

        self.assertFalse(self.user.aa_email_verified)
        self.assertTrue(self.user.sudo().aa_verify_token)
        self.assertIn(self.user.sudo().aa_verify_token,
                      self.user._aa_verification_url())

    # --- the gate ------------------------------------------------------------

    def test_an_unconfirmed_account_cannot_sign_in(self):
        self.user._aa_start_email_verification()

        with self.assertRaises(AccessDenied) as refused:
            self._as_them()._check_credentials(self._credentials(),
                                         {"interactive": True})

        self.assertIn("confirm", str(refused.exception).lower())

    def test_the_refusal_names_the_address_so_the_page_can_say_it(self):
        """Odoo's login page prints the message of an AccessDenied that
        carries one, which is the whole reason this is said here."""
        self.user._aa_start_email_verification()

        with self.assertRaises(AccessDenied) as refused:
            self._as_them()._check_credentials(self._credentials(),
                                         {"interactive": True})

        self.assertIn("unconfirmed@example.com", str(refused.exception))

    def test_a_wrong_password_is_still_just_a_wrong_password(self):
        """THE ORDER MATTERS. The password is checked first, so this page
        never becomes a way of asking whether an address has an account."""
        self.user._aa_start_email_verification()

        with self.assertRaises(AccessDenied) as refused:
            self._as_them()._check_credentials(self._credentials("wrong"),
                                         {"interactive": True})

        self.assertNotIn("confirm", str(refused.exception).lower())

    def test_a_confirmed_account_signs_in_as_before(self):
        self._as_them()._check_credentials(self._credentials(), {"interactive": True})

    # --- spending the link ---------------------------------------------------

    def test_following_the_link_confirms_and_lets_them_in(self):
        self.user._aa_start_email_verification()
        token = self.user.sudo().aa_verify_token

        confirmed = self.env["res.users"]._aa_confirm_email(token)

        self.assertEqual(confirmed, self.user)
        self.assertTrue(self.user.aa_email_verified)
        self._as_them()._check_credentials(self._credentials(), {"interactive": True})

    def test_a_link_works_only_once(self):
        self.user._aa_start_email_verification()
        token = self.user.sudo().aa_verify_token
        self.env["res.users"]._aa_confirm_email(token)

        self.assertFalse(self.env["res.users"]._aa_confirm_email(token))

    def test_an_expired_link_confirms_nothing(self):
        self.user._aa_start_email_verification()
        token = self.user.sudo().aa_verify_token
        self.user.sudo().aa_verify_expiry = fields.Datetime.now() - timedelta(days=1)

        self.assertFalse(self.env["res.users"]._aa_confirm_email(token))
        self.assertFalse(self.user.aa_email_verified, "it let an old link in")

    def test_a_made_up_link_confirms_nothing(self):
        self.user._aa_start_email_verification()

        self.assertFalse(self.env["res.users"]._aa_confirm_email("not-a-token"))
        self.assertFalse(self.env["res.users"]._aa_confirm_email(""))

    # --- the letter itself ---------------------------------------------------

    def test_the_email_carries_a_working_link(self):
        """A confirmation email without the link in it is just a delay."""
        self.user._aa_start_email_verification()
        template = self.env.ref("spring_engineering.mail_template_confirm_email")

        body = template._render_field("body_html", self.user.ids)[self.user.id]

        self.assertIn(self.user.sudo().aa_verify_token, body)
        self.assertIn("/my/confirm-email/", body)


@tagged("post_install", "-at_install")
class TestSigningUpOnTheWebsite(HttpCase):
    """The whole way through, as a stranger does it."""

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c")
        # SIGNUP IS OFF ON THIS SITE BY DEFAULT - the website carries its own
        # auth_signup_uninvited, and AA Impact's is b2b, so /web/signup is a
        # 404 until it is opened. The test says so itself rather than
        # depending on how the database happens to be set.
        self.env["website"].search([]).write({
            "aa_require_email_confirmation": True,
            "auth_signup_uninvited": "b2c",
        })

    def _signup(self, login, follow=True):
        page = self.url_open("/web/signup")
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
        self.assertTrue(token, "no signup form to post")

        return self.url_open("/web/signup", data={
            "csrf_token": token.group(1), "login": login,
            "name": "Website Customer", "password": "s3cret!pw",
            "confirm_password": "s3cret!pw"}, allow_redirects=follow)

    def _user(self, login):
        return self.env["res.users"].sudo().with_context(
            active_test=False).search([("login", "=", login)], limit=1)

    def test_nonsense_makes_no_account(self):
        for nonsense in ("no", "no@", "@no", "no@no", "a b@c.com",
                         "A Customer <a@example.com>"):
            answer = self._signup(nonsense)

            self.assertFalse(self._user(nonsense),
                             "an account was made for %r" % nonsense)
            self.assertIn("valid email address", answer.text,
                          "the page does not say what is wrong")

    def test_the_address_is_stored_as_the_mail_layer_reads_it(self):
        """Otherwise "Me <ME@X.com>" and "me@x.com" are two accounts for one
        mailbox, and the second can never be told why it cannot sign in."""
        self._signup("  TIDY@Example.COM ")

        self.assertTrue(self._user("tidy@example.com"),
                        "the address was not tidied before it was stored")

    def test_a_new_account_is_held_until_it_is_confirmed(self):
        self._signup("stranger@example.com")
        user = self._user("stranger@example.com")

        self.assertTrue(user, "no account was created at all")
        self.assertFalse(user.aa_email_verified)
        self.assertTrue(user.aa_verify_token, "no link was minted")

    def test_the_link_lands_on_a_page_that_says_so(self):
        self._signup("lands@example.com")
        user = self._user("lands@example.com")

        page = self.url_open("/my/confirm-email/%s" % user.aa_verify_token)

        self.assertIn("confirmed", page.text.lower())
        self.assertTrue(self._user("lands@example.com").aa_email_verified)

    def test_a_bad_link_offers_another_one(self):
        page = self.url_open("/my/confirm-email/nonsense")

        self.assertIn("no longer good", page.text.lower())

    def test_each_outcome_has_its_own_title(self):
        """THE TAB USED TO SAY "EMAIL CONFIRMED" EITHER WAY. A controller's
        page has no record of its own, so the layout falls back to the view's
        name - one string for both branches - and somebody turned away by a
        dead link was told in the tab that it had worked."""
        self._signup("titled@example.com")
        user = self._user("titled@example.com")

        def title_of(path):
            found = re.search(r"<title>([^<]*)</title>",
                              self.url_open(path).text)

            return (found.group(1) if found else "").strip()

        self.assertIn("no longer good", title_of("/my/confirm-email/nonsense"))
        self.assertIn("confirmed",
                      title_of("/my/confirm-email/%s" % user.aa_verify_token))

    def test_the_resend_page_never_says_who_has_an_account(self):
        """It would otherwise read the customer list one guess at a time."""
        page = self.url_open("/web/login")
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
        answers = set()

        for login in ("nobody@example.com", "stranger2@example.com"):
            answer = self.url_open("/my/email-confirmation/resend", data={
                "csrf_token": token.group(1), "login": login})
            answers.add(re.sub(r"[\w.@]+@[\w.]+", "", answer.text))

        self.assertEqual(len(answers), 1, "the two answers differ")

    # --- what the owner hit, one by one --------------------------------------

    def test_a_held_signup_redirects_instead_of_rendering(self):
        """ODOO ANSWERS A SIGNUP BY RENDERING THE LOGIN PAGE out of the POST,
        so the browser sits on the result of a POST and reloading re-submits
        it - which fails on a spent token and an address already taken, and
        shows "something went wrong" for pressing F5."""
        answer = self._signup("redirected@example.com", follow=False)

        self.assertIn(answer.status_code, (301, 302, 303), answer.status_code)
        self.assertIn("/my/email-confirmation",
                      answer.headers.get("Location", ""))

    def test_the_page_it_lands_on_says_what_is_waiting(self):
        answer = self._signup("waiting@example.com")

        self.assertIn("confirm your email", answer.text.lower())
        self.assertIn("waiting@example.com", answer.text,
                      "it does not say where the link went")

    def test_that_page_can_be_reloaded(self):
        """The whole point of the redirect."""
        self._signup("reloads@example.com")

        again = self.url_open(
            "/my/email-confirmation?login=reloads@example.com")

        self.assertEqual(again.status_code, 200)
        self.assertIn("confirm your email", again.text.lower())

    def test_only_one_letter_goes_out(self):
        """Odoo sends its own "account created" mail from the signup route,
        whose button confirms nothing - two emails at once, and the owner
        pressed the wrong one."""
        before = self.env["mail.mail"].sudo().search([])
        self._signup("oneletter@example.com")
        sent = self.env["mail.mail"].sudo().search([]) - before

        self.assertEqual(len(sent), 1, sent.mapped("subject"))
        self.assertIn("confirm", (sent.subject or "").lower())

    def test_the_link_in_the_letter_points_at_this_host(self):
        """A link built from web.base.url lands on whatever host that stored
        string names, which is a 404 on any other build - and the token only
        exists in the database they signed up against."""
        self._signup("hosted@example.com")
        user = self._user("hosted@example.com")

        self.assertTrue(
            user._aa_verification_url().startswith(self.base_url()),
            user._aa_verification_url())

    def test_the_signup_box_asks_for_an_email(self):
        page = self.url_open("/web/signup").text
        box = re.search(r'<input[^>]*name="login"[^>]*>', page)

        self.assertTrue(box)
        self.assertIn('type="email"', box.group(0), box.group(0))
