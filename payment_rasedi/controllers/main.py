# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint

from odoo import http
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentPortal

_logger = logging.getLogger(__name__)

class PaymentPortalRasedi(PaymentPortal):
    _return_url = '/payment/rasedi/return'
    _webhook_url = '/payment/rasedi/webhook'
    
    @http.route('/payment/status/poll', type='json', auth='public')
    def poll_status(self):
        """ Override poll_status to actively fetch Rasedi status if needed. """
        _logger.info("Rasedi: poll_status called")
        
        # 1. Get the transaction ID from session
        tx_id = request.session.get('__payment_monitored_tx_id__')
        _logger.info(f"Rasedi: poll_status session tx_id: {tx_id}")
        
        if tx_id:
            tx = request.env['payment.transaction'].sudo().browse(tx_id)
            
            # 2. Check conditions
            if tx.exists() and tx.provider_code == 'rasedi':
                _logger.info(f"Rasedi: poll_status checking tx {tx.reference} (state: {tx.state})")
                if tx.state not in ['done', 'cancel', 'error']:
                    try:
                        _logger.info("Rasedi Polling: Force fetching status for tx %s", tx.reference)
                        tx._rasedi_fetch_transaction_status()
                    except Exception as e:
                        _logger.warning("Rasedi Polling: Failed to fetch status: %s", e)
        
        return super().poll_status()

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def rasedi_return(self, **data):
        """ Handle user return from Rasedi. """
        _logger.info("Rasedi: received data from return URL %s", pprint.pformat(data))
        
        tx = None
        if data:
            try:
                request.env['payment.transaction'].sudo()._handle_notification_data('rasedi', data)
                tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data('rasedi', data)
            except Exception:
                _logger.warning("Rasedi: Error processing return data", exc_info=True)
        
        if not tx:
            # Fallback: Try to find transaction from session
            tx_id = request.session.get('__payment_monitored_tx_id__')
            _logger.info(f"Rasedi: Return fallback session tx_id: {tx_id}")
            if tx_id:
                tx = request.env['payment.transaction'].sudo().browse(tx_id)
        
        # ACTIVE CHECK: Fetch status from API to handle missing/delayed webhooks
        if tx:
            try:
                _logger.info("Rasedi: Force fetching status on return for tx %s", tx.reference)
                tx._rasedi_fetch_transaction_status()
            except Exception as e:
                _logger.warning("Rasedi: Failed to force fetch status on return: %s", e)

        # In Odoo 18, account.payment creation runs via cron (_cron_finalize_post_processing).
        # Trigger it synchronously here so the invoice is reconciled immediately without
        # waiting for the next cron tick.
        if tx:
            try:
                tx = tx.sudo()
                if tx.exists() and tx.state == 'done' and not tx.payment_id:
                    _logger.info("Rasedi: Triggering synchronous payment finalization on return for tx %s", tx.reference)
                    if hasattr(tx, '_finalize_post_processing'):
                        tx._finalize_post_processing()
                    else:
                        tx._create_payment()
            except Exception as e:
                _logger.warning("Rasedi: Return payment finalization failed — cron will retry: %s", e)

        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def rasedi_webhook(self, **data):
        """ Handle webhook from Rasedi. """
        # type='http' does not auto-parse JSON bodies — read and decode manually
        if not data:
            try:
                raw_body = request.httprequest.data
                if raw_body:
                    data = json.loads(raw_body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError) as e:
                _logger.warning("Rasedi: Failed to parse webhook JSON body: %s", e)

        _logger.info("Rasedi: received webhook data %s", pprint.pformat(data))

        if not data:
            _logger.warning("Rasedi: Webhook received empty payload, ignoring")
            return 'OK'

        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('rasedi', data)
        except Exception:
            _logger.exception("Rasedi: webhook processing failed")

        # In Odoo 18, account.payment creation runs via cron (_cron_finalize_post_processing).
        # Trigger it synchronously here so the invoice is reconciled immediately without
        # waiting for the next cron tick.
        try:
            reference = data.get('referenceCode')
            if reference:
                tx = request.env['payment.transaction'].sudo().search([
                    ('provider_reference', '=', reference),
                    ('provider_code', '=', 'rasedi'),
                    ('state', '=', 'done'),
                    ('payment_id', '=', False),
                ], limit=1)
                if tx:
                    _logger.info("Rasedi: Triggering synchronous payment finalization for tx %s", tx.reference)
                    if hasattr(tx, '_finalize_post_processing'):
                        tx._finalize_post_processing()
                    else:
                        tx._create_payment()
        except Exception:
            _logger.warning("Rasedi: Synchronous payment finalization failed — cron will retry", exc_info=True)

        return 'OK'
