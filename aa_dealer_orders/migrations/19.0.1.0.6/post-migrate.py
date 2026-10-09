from odoo import SUPERUSER_ID, api

from odoo.addons.aa_dealer_orders.kit_setup import setup_kit_options


def migrate(cr, version):
    setup_kit_options(api.Environment(cr, SUPERUSER_ID, {}))
