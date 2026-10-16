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
        if request and request.session.get("aa_pending_confirmation"):
            standard = self.env.ref(self.AA_SIGNUP_TEMPLATE,
                                    raise_if_not_found=False)

            if standard and self == standard:
                return False

        return super().send_mail(res_id, **kwargs)
