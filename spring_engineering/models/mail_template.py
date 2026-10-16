from odoo import models
from odoo.http import request


class MailTemplate(models.Model):
    """One letter about a new account, not two that disagree.

    Odoo's signup route sends "your account has been created" itself, with a
    button to the partner's signup url. While this module is holding the
    account for confirmation that letter is worse than redundant: the
    customer gets two emails at once, and the standard one's button does not
    confirm anything - it goes somewhere that cannot help them, which is
    exactly what the owner hit when he pressed it.

    So it is held back for the one request that is creating a held account.
    The flag is set as the account is made and cleared at the end of the same
    request, so nothing else this template is used for is affected.
    """

    _inherit = "mail.template"

    AA_SIGNUP_TEMPLATE = "auth_signup.mail_template_user_signup_account_created"

    def send_mail(self, res_id, **kwargs):
        pending = request.session.get("aa_pending_confirmation") if request else None

        if pending:
            standard = self.env.ref(self.AA_SIGNUP_TEMPLATE,
                                    raise_if_not_found=False)
            # THE ONE ACCOUNT BEING HELD, not every send that happens to
            # share the request. Matching the record as well as the template
            # keeps this from reaching any other letter sent along the way.
            held = self.env["res.users"].sudo().browse(res_id).exists()

            if standard and self == standard and held and held.login == pending:
                # send_mail answers with the id of the mail it created, so
                # the honest answer for one that was never created is no id.
                return 0

        return super().send_mail(res_id, **kwargs)
