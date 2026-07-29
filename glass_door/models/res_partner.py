from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_dealer = fields.Boolean('Is Dealer', default=False)
    dealer_markup = fields.Float('Dealer Markup (%)', digits=(5, 2), default=0.0,
                                  help='Markup percentage applied on top of cost for this dealer.')
