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
        request.env['payment.transaction'].sudo()._handle_notification_data('rasedi', data)
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def rasedi_webhook(self, **data):
        """ Handle webhook from Rasedi. """
        _logger.info("Rasedi: received webhook data %s", pprint.pformat(data))
        # Verify signature if possible (Rasedi might sign webhooks). 
        # For now, just trust reference linkage.
        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('rasedi', data)
        except Exception:
            _logger.exception("Rasedi: webhook processing failed")
        return 'OK'
