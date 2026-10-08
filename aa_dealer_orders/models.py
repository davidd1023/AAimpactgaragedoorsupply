from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

ON_ACCOUNT = 'on_account'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    aa_order_on_account = fields.Boolean(
        string="Preferred Dealer - Order on Account",
        tracking=True,
        help="This dealer can place orders without paying at checkout (\"Charge to Account\") "
             "and use the Quick Order page (/dealer/order). Set it on the company; its "
             "contacts inherit it.",
    )
    aa_dealer_margin = fields.Float(
        string="Dealer Margin over Cost (%)",
        digits=(5, 2),
        tracking=True,
        help="Dealer price = product cost + this margin. Change it any time: the dealer's "
             "own pricelist is updated automatically. Leave 0 to keep the normal store prices.",
    )
    aa_dealer_pricelist_id = fields.Many2one(
        'product.pricelist', string="Dealer Pricelist", readonly=True, copy=False,
        help="Pricelist managed automatically from the dealer margin.",
    )

    def _aa_is_on_account_dealer(self):
        """True when this contact or its company is flagged as an on-account dealer."""
        self.ensure_one()
        return bool(self.aa_order_on_account or self.commercial_partner_id.aa_order_on_account)

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners.filtered(lambda p: p.aa_dealer_margin)._aa_sync_dealer_pricelist()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if 'aa_dealer_margin' in vals or 'aa_order_on_account' in vals:
            self._aa_sync_dealer_pricelist()
        return res

    def _aa_sync_dealer_pricelist(self):
        """Keep one 'Dealer - <name>' pricelist per dealer: cost + margin %, on every product."""
        website = self.env['website'].sudo().search([('company_id', '=', self.env.company.id)], limit=1)
        for partner in self.sudo():
            if not partner.aa_order_on_account or not partner.aa_dealer_margin:
                continue
            pricelist = partner.aa_dealer_pricelist_id
            item_vals = {
                'applied_on': '3_global',
                'compute_price': 'formula',
                'base': 'standard_price',
                'price_markup': partner.aa_dealer_margin,
            }
            if not pricelist:
                pricelist = self.env['product.pricelist'].sudo().create({
                    'name': f"Dealer - {partner.name}",
                    'selectable': False,
                    'website_id': website.id or False,
                    'item_ids': [Command.create(item_vals)],
                })
                partner.aa_dealer_pricelist_id = pricelist
            else:
                items = pricelist.item_ids.filtered(lambda i: i.applied_on == '3_global')
                if items:
                    items[:1].write(item_vals)
                else:
                    pricelist.item_ids = [Command.create(item_vals)]
            if partner.property_product_pricelist != pricelist:
                partner.property_product_pricelist = pricelist


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    aa_dealer_quick_order = fields.Boolean(
        string="Dealer Quick Order",
        help="Show this product on the dealer Quick Order page (/dealer/order).",
    )


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    aa_dealer_quick_order = fields.Boolean(
        string="Dealer Quick Order", readonly=True, copy=False,
        help="Placed by a dealer from the Quick Order page.",
    )




class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    custom_mode = fields.Selection(
        selection_add=[(ON_ACCOUNT, "Charge to Account (Dealers)")],
        ondelete={ON_ACCOUNT: 'set null'},
    )

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.custom_mode != ON_ACCOUNT:
            return super()._get_default_payment_method_codes()
        return {ON_ACCOUNT}

    @api.model
    def _aa_on_account_allowed(self, partner_id, sale_order_id=None):
        """On account is only for flagged dealers paying a sales order of their own."""
        if not sale_order_id:
            return False  # e.g. paying an invoice or a payment link: never on account
        partner = self.env['res.partner'].sudo().browse(partner_id).exists()
        order = self.env['sale.order'].sudo().browse(sale_order_id).exists()
        if not partner or not order:
            return False
        return (
            partner._aa_is_on_account_dealer()
            and order.partner_id.commercial_partner_id == partner.commercial_partner_id
        )

    @api.model
    def _get_compatible_providers(
        self, company_id, partner_id, amount, *args, sale_order_id=None, report=None, **kwargs
    ):
        providers = super()._get_compatible_providers(
            company_id, partner_id, amount, *args,
            sale_order_id=sale_order_id, report=report, **kwargs,
        )
        if not self._aa_on_account_allowed(partner_id, sale_order_id):
            unfiltered = providers
            providers = providers.filtered(lambda p: p.custom_mode != ON_ACCOUNT)
            payment_utils.add_to_report(
                report, unfiltered - providers, available=False,
                reason=_("only available to preferred dealers"),
            )
        return providers


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model_create_multi
    def create(self, vals_list):
        txs = super().create(vals_list)
        for tx in txs.filtered(lambda t: t.provider_id.custom_mode == ON_ACCOUNT):
            orders = tx.sale_order_ids
            if not orders or not tx.partner_id._aa_is_on_account_dealer() or any(
                o.partner_id.commercial_partner_id != tx.partner_id.commercial_partner_id
                for o in orders
            ):
                raise ValidationError(_("Charge to Account is only available to preferred dealers."))
        return txs

    def _post_process(self):
        """Orders charged to a dealer account are confirmed right away (no payment needed)."""
        on_account_txs = self.filtered(
            lambda tx: tx.provider_id.custom_mode == ON_ACCOUNT and tx.state == 'pending'
        )
        on_account_txs.sale_order_ids.filtered(
            lambda so: so.state in ('draft', 'sent')
        ).with_context(send_email=True).action_confirm()
        super()._post_process()
