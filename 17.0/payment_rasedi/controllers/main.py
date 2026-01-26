# Part of Odoo. See LICENSE file for full copyright and licensing details.

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
        
        # Try to redirect to invoice if possible
        # Try to redirect to invoice if possible - DISABLED for now to prevent login issues
        # Public users cannot access report download URLs directly without token.
        # try:
        #     if tx and tx.state == 'done' and tx.invoice_ids:
        #         invoice = tx.invoice_ids[0]
        #         if invoice.state == 'posted':
        #             return request.redirect(f'/report/pdf/account.report_invoice/{invoice.id}')
        # except Exception:
        #     _logger.warning("Rasedi: Could not redirect to invoice, falling back to status page.")

        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def rasedi_webhook(self, **data):
        """ Handle webhook from Rasedi. """
        # Rasedi sends JSON body, which Odoo's type='http' doesn't auto-parse into **data
        if not data:
            try:
                data = request.get_json_data()
            except Exception:
                pass
        
        _logger.info("Rasedi: received webhook data %s", pprint.pformat(data))
        
        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('rasedi', data)
        except Exception:
            _logger.exception("Rasedi: webhook processing failed")
        return 'OK'
