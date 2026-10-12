from odoo import SUPERUSER_ID, api

from odoo.addons.aa_dealer_orders.kit_setup import retire_old_kit_page_script


def migrate(cr, version):
    retire_old_kit_page_script(api.Environment(cr, SUPERUSER_ID, {}))
