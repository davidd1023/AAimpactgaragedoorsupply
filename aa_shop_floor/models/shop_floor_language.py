"""ENGLISH OR SPANISH, PER USER, FROM THE SHOP FLOOR (owner, 2026-11-11).

"un boton que se le pueda cambiar a espanol o ingles en shop floor para cada
usuario" - a button in the Shop Floor's menu that switches the signed-in
user between English and Spanish.

THE LANGUAGE IS THE USER'S OWN ODOO LANGUAGE, not a setting of ours: Jorge's
tablet signs in as Jorge, so changing it on his tablet changes it for him and
nobody else, and Odoo's own Shop Floor - every button it ships - follows it
for free. Our own words come from i18n/es.po.

SPANISH IS LATIN AMERICAN (es_419), Odoo's generic Spanish. It is switched on
the first time anybody asks for it, so nothing has to be installed by hand.
"""

from odoo import _, api, models
from odoo.exceptions import UserError

SHOP_FLOOR_LANGS = {"en": "en_US", "es": "es_419"}


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def aa_set_shop_floor_language(self, code):
        """Switch the signed-in user to English ('en') or Spanish ('es')."""
        lang = SHOP_FLOOR_LANGS.get(code)
        if not lang:
            raise UserError(_("Unknown language: %s", code))
        Lang = self.env["res.lang"].sudo()
        if not Lang._get_code(lang):
            Lang._activate_lang(lang)
        if not Lang._get_code(lang):
            raise UserError(_("The %s language is not available on this database.", lang))
        # A user may always change his own language (it is on his
        # Preferences); sudo only so a worker login is never refused it.
        self.env.user.sudo().lang = lang
        return code
