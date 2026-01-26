# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # 1. Get the Rasedi Provider
    rasedi_provider = env.ref('payment_rasedi.payment_provider_rasedi', raise_if_not_found=False)
    if not rasedi_provider:
        _logger.warning("Rasedi: Provider not found during post_init.")
        return

    # 2. Get the Payment Method (Electronic or Manual)
    # In Odoo 16, typically 'account.account_payment_method_electronic_in' is used for online providers.
    payment_method = env.ref('account.account_payment_method_electronic_in', raise_if_not_found=False)
    
    if not payment_method:
         # Fallback
         payment_method = env.ref('account.account_payment_method_manual_in', raise_if_not_found=False)

    if not payment_method:
        _logger.warning("Rasedi: Could not find 'electronic' or 'manual' payment method. Setup skipped.")
        return

    # 3. Add to Bank Journals
    # Find all Bank journals that don't already have Rasedi configured
    bank_journals = env['account.journal'].search([('type', '=', 'bank')])
    
    for journal in bank_journals:
        # Check if line already exists for this provider
        existing = env['account.payment.method.line'].search([
            ('journal_id', '=', journal.id),
            ('payment_provider_id', '=', rasedi_provider.id)
        ])
        if not existing:
            _logger.info(f"Rasedi: Adding payment method line to journal {journal.name}")
            try:
                env['account.payment.method.line'].create({
                    'name': 'Rasedi',
                    'journal_id': journal.id,
                    'payment_method_id': payment_method.id,
                    'payment_provider_id': rasedi_provider.id,
                })
            except Exception as e:
                _logger.warning(f"Rasedi: Failed to add line to journal {journal.name}: {e}")
