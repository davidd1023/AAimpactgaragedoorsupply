"""ENGLISH OR SPANISH FROM THE SHOP FLOOR (owner, 2026-11-11)."""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class ShopFloorLanguageCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.worker = new_test_user(
            self.env, login="aa_lang_worker",
            groups="base.group_user,mrp.group_mrp_user,aa_shop_floor.group_shop_floor_only")

    def test_a_worker_switches_himself_to_spanish_and_back(self):
        Users = self.env["res.users"].with_user(self.worker)
        Users.aa_set_shop_floor_language("es")
        self.assertEqual(self.worker.lang, "es_419")
        Users.aa_set_shop_floor_language("en")
        self.assertEqual(self.worker.lang, "en_US")

    def test_only_his_own_language_changes(self):
        admin = self.env.ref("base.user_admin")
        before = admin.lang
        self.env["res.users"].with_user(self.worker).aa_set_shop_floor_language("es")
        self.assertEqual(admin.lang, before)

    def test_an_unknown_language_is_refused(self):
        with self.assertRaises(UserError):
            self.env["res.users"].with_user(self.worker).aa_set_shop_floor_language("fr")

    def test_our_buttons_have_spanish(self):
        terms = {m["id"]: m["string"] for m in
                 code_translations.get_web_translations("aa_shop_floor", "es_419")["messages"]}
        self.assertEqual(terms.get("Change track"), "Cambiar track")
        self.assertEqual(terms.get("Mark as Done"), "Marcar como hecho")
        self.assertEqual(terms.get("Cut to"), "Cortar a")
