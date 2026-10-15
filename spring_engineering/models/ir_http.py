from odoo import models


class IrHttp(models.AbstractModel):
    """Send this module's translations to the SHOP, not only to the back office.

    A TRANSLATION FILE IS NOT ENOUGH ON ITS OWN. The website does not hand the
    browser every installed module's terms - it asks
    get_translation_frontend_modules() for a list, and sends only those. A
    module that never puts its name on that list has its .po read on the
    server and never sent to the page, which looks exactly like having no
    translation file at all.

    That is what happened here: es.po was loaded, every term was correct, and
    the calculator still drew itself in English - except for the words Odoo
    happened to translate for some other module. Those arrive through the
    GLOBAL pool, which is the fallback when the module's own context has
    nothing:

        translatedTerms[module][source] ?? translatedTermsGlobal[source] ?? source

    which is why "Single" came out as "Soltero(a)" - the marital status, from
    website's own file - while "Spring ID" and "Lift Type", which no other
    module has any reason to translate, stayed in English.
    """

    _inherit = "ir.http"

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        return super()._get_translation_frontend_modules_name() + [
            "spring_engineering",
        ]
