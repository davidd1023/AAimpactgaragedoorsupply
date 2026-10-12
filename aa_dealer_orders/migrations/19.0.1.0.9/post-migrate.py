from odoo import SUPERUSER_ID, api

from odoo.addons.aa_dealer_orders.kit_setup import refresh_prepared_costs


def migrate(cr, version):
    refresh_prepared_costs(api.Environment(cr, SUPERUSER_ID, {}))
