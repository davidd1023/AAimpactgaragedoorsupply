import secrets
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import AccessDenied
from odoo.http import request


class ResUsers(models.Model):
    """An account is not an account until the address behind it answers.

    Anyone could sign up with "no" in the email box - Odoo's signup form is a
    text field and its controller takes what it is given - so the shop could
    collect customers nobody can ever reach, and an order could be placed
    against an address that does not exist.

    Two separate things fix that, and both are needed: the address has to LOOK
    like an address, which the signup controller now checks, and it has to BE
    one, which only a letter to it can prove.
    """

    _inherit = "res.users"

    # TRUE BY DEFAULT, WHICH IS WHAT GRANDFATHERS EVERYBODY. Adding a column
    # fills the existing rows with its default, so every account that already
    # exists is confirmed the moment this deploys and nobody is locked out of
    # an account they have been using for months. It is also right for users
    # the back office creates: an address typed by the owner is not a stranger
    # claiming to own one. Only the website's own signup sets it False.
    aa_email_verified = fields.Boolean(
        string="Email confirmed",
        default=True,
        copy=False,
        help="Cleared when somebody signs up on the website, and set again"
             " when they follow the link sent to the address they gave. An"
             " account cannot be signed in to until it is set.",
    )

    # THE SECRET, kept from everybody but the system. It is the whole of the
    # proof, so it is read and written through sudo by the code that sends and
    # checks it, and is never rendered on a page.
    aa_verify_token = fields.Char(copy=False, groups="base.group_system")
    aa_verify_expiry = fields.Datetime(copy=False, groups="base.group_system")
    # When the last letter went out, so asking again cannot be used to post
    # one person an unlimited number of them.
    aa_verify_sent_at = fields.Datetime(copy=False, groups="base.group_system")

    # Long enough to survive a weekend and a spam folder, short enough that a
    # link found later in a forwarded mailbox is no longer a key.
    AA_VERIFY_VALID_FOR = timedelta(days=3)

    # The least time between two letters to the same address. Long enough that
    # nobody can be buried, short enough that a customer who pressed the
    # button too early is not left waiting.
    AA_VERIFY_RESEND_EVERY = timedelta(minutes=2)

    def _aa_start_email_verification(self):
        """Mark the account unconfirmed, mint a link and send it."""
        self.ensure_one()
        self.sudo().write({
            "aa_email_verified": False,
            "aa_verify_token": secrets.token_urlsafe(32),
            "aa_verify_expiry": fields.Datetime.now() + self.AA_VERIFY_VALID_FOR,
            "aa_verify_sent_at": fields.Datetime.now(),
        })
        self._aa_send_verification_email()

    def _aa_resend_verification(self):
        """Send the link again - THE SAME LINK, and not too often.

        THE SAME ONE, because minting a fresh token kills the letter already
        in their inbox: somebody who presses "send it again" and then finds
        the first email is told their link is dead, which is nonsense and
        looks like a broken shop. A new token is minted only when there is no
        usable one left.

        AND NOT TOO OFTEN, because this can be asked for by anybody who knows
        an address - without a floor it is a way of posting a stranger as
        many emails as you like. Refusing is silent: the page says the same
        thing either way, so a caller still learns nothing about who has an
        account.

        Returns True when a letter actually went out.
        """
        self.ensure_one()
        user = self.sudo()
        now = fields.Datetime.now()

        if user.aa_verify_sent_at and now - user.aa_verify_sent_at < self.AA_VERIFY_RESEND_EVERY:
            return False

        spent = not user.aa_verify_token or (
            user.aa_verify_expiry and user.aa_verify_expiry < now)

        if spent:
            user.write({
                "aa_verify_token": secrets.token_urlsafe(32),
                "aa_verify_expiry": now + self.AA_VERIFY_VALID_FOR,
            })

        user.write({"aa_verify_sent_at": now})
        self._aa_send_verification_email()

        return True

    def _aa_send_verification_email(self):
        self.ensure_one()
        template = self.env.ref(
            "spring_engineering.mail_template_confirm_email",
            raise_if_not_found=False)

        if template:
            template.sudo().send_mail(self.id, force_send=True)

    def _aa_verification_url(self):
        """The link, on the host the customer is actually using.

        NOT get_base_url() ALONE. That reads web.base.url, a single stored
        string for the whole database, and a link built from it lands on
        whatever host that string names - which is the wrong server whenever
        it has drifted, and a 404 even when the code is deployed, because the
        token only exists in the database the customer signed up against.
        The address they are standing on cannot be wrong, so it is used when
        there is a request to read it from.
        """
        self.ensure_one()
        base = (request.httprequest.url_root.rstrip("/")
                if request else self.get_base_url())

        return "%s/my/confirm-email/%s" % (base, self.sudo().aa_verify_token or "")

    def _aa_find_verification(self, token):
        """The account a link belongs to, WITHOUT spending it.

        Reading and spending are separate because the link arrives by email,
        and a link in an email is fetched by things that are not the
        customer: scanners, previewers and security gateways all follow it
        before a human sees it. When following it was enough to use it up,
        those made the customer's own click fail - see the controller, which
        now reads on GET and spends on POST.
        """
        Users = self.env["res.users"].sudo()

        if not token:
            return Users.browse()

        user = Users.search([("aa_verify_token", "=", token)], limit=1)

        if not user:
            return Users.browse()

        if user.aa_verify_expiry and user.aa_verify_expiry < fields.Datetime.now():
            return Users.browse()

        return user

    def _aa_confirm_email(self, token):
        """Spend a confirmation link.

        Returns the user it confirmed, or an empty recordset for a link that
        is unknown, already spent or out of date - all three of which the
        page answers the same way, with the offer of a fresh one. A link that
        has been used is no different from one that never existed: the token
        is cleared the moment it works, so it cannot be replayed.
        """
        user = self._aa_find_verification(token)

        if not user:
            return user

        user.write({
            "aa_email_verified": True,
            "aa_verify_token": False,
            "aa_verify_expiry": False,
        })

        return user

    def _check_credentials(self, credential, env):
        """Refuse an unconfirmed account, and say so.

        AFTER super(), DELIBERATELY. The password is checked first, so this
        only ever speaks to somebody who already knows it - which means
        naming the reason gives nothing away to a stranger guessing at
        addresses. Refusing before the password was checked would turn this
        page into a way of asking "does this account exist".

        Odoo's login page prints the message of an AccessDenied that carries
        one, so the customer is told what to do instead of being shown "wrong
        login/password" for a password that was right.
        """
        auth_info = super()._check_credentials(credential, env)
        user = self.env["res.users"].sudo().browse(auth_info["uid"])

        if user.aa_email_verified:
            return auth_info

        # So the sign-in page can offer to send another one without asking
        # for the address again.
        if request:
            request.session["aa_unconfirmed_login"] = user.login

        raise AccessDenied(_(
            "Please confirm your email address before signing in. We sent a"
            " link to %(email)s when the account was created.",
            email=user.login,
        ))
