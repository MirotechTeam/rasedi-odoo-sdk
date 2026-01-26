# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class RasediController(http.Controller):
    _return_url = '/payment/rasedi/return'
    _webhook_url = '/payment/rasedi/webhook'

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False, save_session=False)
    def rasedi_return(self, **data):
        """ Handle user return from Rasedi. """
        _logger.info("Rasedi: received data from return URL %s", pprint.pformat(data))
        # Rasedi usually redirects with referenceCode or status params
        # We need to process it.
        # But commonly we just redirect to status page directly if webhook handles logic.
        # However, checking status here is safe.
        tx = None
        if data:
            # Capture the transaction linked to this data
            try:
                request.env['payment.transaction'].sudo()._handle_notification_data('rasedi', data)
                tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data('rasedi', data)
            except Exception:
                _logger.warning("Rasedi: Error processing return data", exc_info=True)
        
        if not tx:
            # Fallback: Try to find transaction from session
            tx_id = request.session.get('__payment_monitored_tx_id__')
            if tx_id:
                tx = request.env['payment.transaction'].sudo().browse(tx_id)
        
        # Try to redirect to invoice if possible
        try:
            if tx and tx.state == 'done' and tx.invoice_ids:
                invoice = tx.invoice_ids[0]
                if invoice.state == 'posted':
                    return request.redirect(f'/report/pdf/account.report_invoice/{invoice.id}')
        except Exception:
            _logger.warning("Rasedi: Could not redirect to invoice, falling back to status page.")

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
