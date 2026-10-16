import logging

from odoo import _, http
from odoo.exceptions import UserError
from werkzeug.urls import url_encode

from odoo.http import request
from odoo.tools.mail import email_normalize, single_email_re

from odoo.addons.auth_signup.controllers.main import AuthSignupHome

_logger = logging.getLogger(__name__)


class SignupNeedsARealAddress(AuthSignupHome):
    """Signing up should be easy, but not free of any check at all.

    Odoo renders the signup field as <input type="text" name="login"> under a
    label reading Email, and its controller passes whatever was typed
    straight to res.users.signup, which only checks that something was given.
    "no" was a perfectly good account.
    """

    def _prepare_signup_values(self, qcontext):
        """THE ADDRESS HAS TO LOOK LIKE ONE, checked here rather than on the
        page, because the page can be skipped: this route answers a POST from
        anywhere.

        email_normalize is Odoo's own reader of addresses - the one the mail
        layer uses to decide what it can send to - so an address this accepts
        is one the shop can actually write to, and nothing else is let in.
        """
        values = super()._prepare_signup_values(qcontext)
        values["login"] = self._aa_email_or_raise(values.get("login"))

        return values

    def _aa_email_or_raise(self, login):
        """The address, as the mail layer reads it, or a refusal.

        SEPARATE FROM THE CALLER ABOVE so it can be tested without a browser:
        Odoo's own _prepare_signup_values reaches for request.env to work out
        the language, so it cannot be called at all outside a real request,
        and the rule worth testing here is this one.

        Lower case, trimmed, and without a display name wrapped round it -
        otherwise "Me <ME@x.com>" and "me@x.com" are two accounts for one
        mailbox, and the second can never be told why it cannot sign in.
        """
        raw = (login or "").strip()

        # CHECKED BEFORE IT IS TIDIED, and checked with the strict pattern.
        # email_normalize is a normaliser, not a judge: it passes "@no" and
        # "no@no" unchanged, and it turns "a b@c.com" into "b@c.com" without
        # a word - which would have made an account at an address the
        # customer never typed. single_email_re is the strict one, and
        # running it on the RAW text means nothing is quietly rewritten into
        # something acceptable.
        if not single_email_re.match(raw):
            raise UserError(_(
                "Please enter a valid email address - we send your order"
                " confirmation and your receipt to it."
            ))

        return email_normalize(raw) or raw.lower()

    def _signup_with_values(self, token, values, do_login):
        """A SELF-MADE ACCOUNT IS NOT SIGNED IN UNTIL THE ADDRESS ANSWERS.

        An INVITED user is a different matter and keeps Odoo's behaviour: the
        shop sent them their link, so the address is already proven and
        making them prove it again would be asking them to confirm the very
        mailbox the invitation arrived in.

        Not logging them in is most of the rule - the rest is
        res.users._check_credentials, which refuses the sign-in they are
        bounced to afterwards and tells them why.
        """
        if token or not self._aa_confirmation_required():
            return super()._signup_with_values(token, values, do_login)

        super()._signup_with_values(token, values, do_login=False)

        Users = request.env["res.users"].sudo()
        user = Users.search(
            Users._get_login_domain(values.get("login")),
            order=Users._get_login_order(), limit=1)

        if user:
            # SET BEFORE THE LETTER GOES OUT. mail_template.py reads this to
            # hold back Odoo's own "account created" email, which would
            # otherwise arrive alongside ours offering a button that confirms
            # nothing.
            request.session["aa_pending_confirmation"] = user.login
            user._aa_start_email_verification()

    def _aa_confirmation_required(self):
        website = getattr(request, "website", None)

        return bool(website and website.aa_require_email_confirmation)

    @http.route()
    def web_auth_signup(self, *args, **kw):
        """Finish a held signup on a page of its own.

        ODOO ANSWERS A SIGNUP BY RENDERING, NOT REDIRECTING: it returns the
        login page straight out of the POST. That is survivable when the
        signup logged you in, because you are immediately sent on - but when
        the account is held, the browser is left sitting on the RESULT OF A
        POST. Reloading re-submits it, the second attempt fails on a token
        that has been spent and an address already taken, and the customer is
        shown "something went wrong" for doing nothing worse than pressing
        F5. That is what the owner hit.

        So a held signup answers with a redirect to a page that says what is
        waiting for them, which a browser can reload all day.
        """
        response = super().web_auth_signup(*args, **kw)
        pending = request.session.pop("aa_pending_confirmation", None)

        if pending:
            return request.redirect(
                "/my/email-confirmation?" + url_encode({"login": pending}))

        return response

    # --- spending the link ---------------------------------------------------

    @http.route("/my/confirm-email/<string:token>", type="http", auth="public",
                website=True, sitemap=False)
    def aa_confirm_email(self, token, **kw):
        user = request.env["res.users"]._aa_confirm_email(token)

        if user:
            _logger.info("Email confirmed for <%s>", user.login)
            request.session.pop("aa_unconfirmed_login", None)

        return request.render("spring_engineering.aa_email_confirmed", {
            "confirmed": bool(user),
            "login": user.login if user else
                     request.session.get("aa_unconfirmed_login", ""),
        })

    @http.route("/my/email-confirmation", type="http", auth="public",
                website=True, sitemap=False)
    def aa_email_confirmation_pending(self, **kw):
        """Where a new customer lands: what is waiting, and how to chase it."""
        return request.render("spring_engineering.aa_email_confirm_pending", {
            "login": (kw.get("login") or "").strip(),
        })

    @http.route("/my/email-confirmation/resend", type="http", auth="public",
                website=True, sitemap=False, methods=["GET", "POST"])
    def aa_resend_confirmation(self, **kw):
        """Send another link, without saying whether there was anyone to send to.

        THE ANSWER IS THE SAME EITHER WAY. A page that said "no such account"
        would be a way of testing addresses against the customer list, and a
        page that said "already confirmed" would be a way of testing which of
        them are real. Somebody who owns the mailbox finds out by looking in
        it.
        """
        login = (kw.get("login")
                 or request.session.get("aa_unconfirmed_login") or "").strip()

        if request.httprequest.method == "POST" and login:
            Users = request.env["res.users"].sudo()
            user = Users.search(
                Users._get_login_domain(login),
                order=Users._get_login_order(), limit=1)

            if user and not user.aa_email_verified:
                user._aa_start_email_verification()

            return request.render("spring_engineering.aa_email_confirm_sent",
                                  {"login": login})

        return request.render("spring_engineering.aa_email_confirm_resend",
                              {"login": login})
