from odoo import models, fields, api


class GlassDoorDealerClient(models.Model):
    _name = 'glass.door.dealer.client'
    _description = 'Dealer Client'
    _order = 'name'

    name = fields.Char('Client Name', required=True)
    dealer_id = fields.Many2one('res.partner', 'Dealer', required=True,
                                 default=lambda self: self.env.user.partner_id,
                                 domain=[('is_dealer', '=', True)])
    markup = fields.Float(
        'Client Markup (%)', digits=(5, 2), default=0.0,
        help='Default markup applied when this client is selected on a quote. '
             'Only visible here — never shown on the quote form.'
    )
    phone = fields.Char('Phone')
    email = fields.Char('Email')
    note = fields.Text('Notes')

    # Computed: number of orders for this client
    order_count = fields.Integer(compute='_compute_order_count', string='Orders')

    def _compute_order_count(self):
        for client in self:
            client.order_count = self.env['glass.door.order'].search_count([
                ('dealer_client_id', '=', client.id)
            ])

    @api.model
    def _get_dealer_domain(self):
        """Return only clients belonging to the current portal dealer."""
        return [('dealer_id', '=', self.env.user.partner_id.id)]
