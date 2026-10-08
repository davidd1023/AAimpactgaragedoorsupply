from . import controllers
from . import models
from .kit_setup import setup_kit_options

from odoo.addons.payment import reset_payment_provider

# Kits that appear on the Quick Order page right after install. More products can be
# added later with the "Dealer Quick Order" checkbox on the product form.
QUICK_ORDER_KITS = ['AA-1200 Hardware Kit', 'AA-1600 Hardware Kit', 'AA-1800 Hardware Kit']


def post_init_hook(env):
    kits = env['product.template'].with_context(active_test=False).search(
        [('name', 'in', QUICK_ORDER_KITS)]
    )
    kits.write({'aa_dealer_quick_order': True})
    setup_kit_options(env)


def uninstall_hook(env):
    reset_payment_provider(env, 'custom', custom_mode='on_account')
