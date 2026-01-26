# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)



class PaymentProviderRasediGateway(models.Model):
    _name = 'payment.provider.rasedi.gateway'
    _description = 'Rasedi Payment Gateway'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('rasedi', 'Rasedi')], ondelete={'rasedi': 'set default'})
    rasedi_secret_key = fields.Char(string='Rasedi Secret Key', required_if_provider='rasedi', groups='base.group_system')
    rasedi_private_key = fields.Text(string='Rasedi Private Key', required_if_provider='rasedi', groups='base.group_system')
    
    # Configuration
    rasedi_gateway_ids = fields.Many2many('payment.provider.rasedi.gateway', string='Allowed Gateways')
    rasedi_collect_fee = fields.Boolean(string='Collect Fee from Customer', default=True)
    rasedi_collect_email = fields.Boolean(string='Collect Customer Email', default=True)
    rasedi_collect_phone = fields.Boolean(string='Collect Customer Phone', default=True)

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'rasedi':
            # Rasedi likely supports multiple, but let's default to all valid for now.
             supported_currencies = self.env['res.currency'].search([('active', '=', True)])
        return supported_currencies
