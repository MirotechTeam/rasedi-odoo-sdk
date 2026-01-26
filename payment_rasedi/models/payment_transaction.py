# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import json
import base64
import requests
from urllib.parse import urlparse

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return the values for Rasedi payment. """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'rasedi':
            return res

        api_url = 'https://stage.api.rasedi.com/v1/payment/rest/live/create'
        
        base_url = self.provider_id.get_base_url()
        
        # Enforce HTTPS and clean up double protocols
        # Odoo inside Docker often thinks it is HTTP, but behind a tunnel (pinggy) it is HTTPS.
        # Rasedi/Browsers dislike mixing, so we force HTTPS for the callback.
        if base_url.startswith('http://'):
            base_url = base_url.replace('http://', 'https://', 1)
        
        # Strip trailing slash
        if base_url.endswith('/'):
            base_url = base_url[:-1]
            
        return_url = f"{base_url}/payment/rasedi/return"
        webhook_url = f"{base_url}/payment/rasedi/webhook"

        selected_gateways = self.provider_id.rasedi_gateway_ids.mapped('code')
        if not selected_gateways:
            # Fallback if none selected, though admin should really select some.
            selected_gateways = ["CREDIT_CARD"] 

        payload = {
            'amount': str(int(self.amount)), 
            'title': self.reference or "Order",
            'description': f"Order {self.reference}",
            'gateways': selected_gateways,
            'redirectUrl': return_url,
            'callbackUrl': webhook_url,
            'collectFeeFromCustomer': self.provider_id.rasedi_collect_fee,
            'collectCustomerEmail': self.provider_id.rasedi_collect_email,
            'collectCustomerPhoneNumber': self.provider_id.rasedi_collect_phone
        }

        # Explicitly log the constructed payload for debugging
        _logger.info("Rasedi: CONSTRUCTED PAYLOAD: %s", json.dumps(payload))

        # Signing
        secret_key = self.provider_id.rasedi_secret_key
        private_key = self.provider_id.rasedi_private_key
        
        if not secret_key or secret_key == 'dummy' or not private_key or private_key == 'dummy':
             raise ValidationError("Rasedi: Please configure the Secret Key and Private Key in the Payment Provider settings.")
        
        relative_path = "/v1/payment/rest/live/create"
        
        raw_sign = f"POST || {secret_key} || {relative_path}"
        signature = self._rasedi_sign(raw_sign, private_key)

        headers = {
            'Content-Type': 'application/json',
            'x-id': secret_key,
            'x-signature': signature
        }

        _logger.warning("Rasedi Request URL: %s", api_url)
        _logger.warning("Rasedi Request Headers: %s", json.dumps(headers))
        _logger.warning("Rasedi Request Payload: %s", json.dumps(payload))

        try:
            req = requests.post(api_url, json=payload, headers=headers, timeout=20)
            req.raise_for_status()
            response_data = req.json()
            redirect_url = response_data.get('redirectUrl')
            
            if not redirect_url:
                 raise ValidationError("Rasedi: No redirect URL received")
            
            # Save reference code
            self.provider_reference = response_data.get('referenceCode')
            
            # Return URL for Odoo to redirect
            return {'api_url': redirect_url}

        except Exception as e:
            _logger.error("Rasedi Error: %s", str(e))
            raise ValidationError("Rasedi Payment Creation Failed: " + str(e))

    def _rasedi_sign(self, raw_data, private_key_pem):
        """ Sign data using Ed25519. """
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519
            
            # Load Private Key
            # Assuming PEM format
            if "-----BEGIN PRIVATE KEY-----" not in private_key_pem:
                 # maybe it is just base64 encoded without headers?
                 pass 

            priv_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None
            )
            
            if not isinstance(priv_key, ed25519.Ed25519PrivateKey):
                # Odoo environments might vary, but users supplied Ed25519 keys
                raise ValidationError("Key is not Ed25519")

            signature = priv_key.sign(raw_data.encode('utf-8'))
            return base64.b64encode(signature).decode('utf-8')

        except ImportError:
            # Fallback if cryptography is old or missing Ed25519
            # Try to use pure python if we had it, but here we raise error
            raise ValidationError("Rasedi: 'cryptography' library with Ed25519 support is required.")
        except Exception as e:
            raise ValidationError(f"Rasedi Signing Error: {str(e)}")

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Find the transaction based on Rasedi data. """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'rasedi' or len(tx) == 1:
            return tx

        reference = notification_data.get('referenceCode') or notification_data.get('reference')
        if not reference:
            raise ValidationError("Rasedi: No reference in notification data")

        tx = self.search([('provider_reference', '=', reference), ('provider_code', '=', 'rasedi')])
        if not tx:
            raise ValidationError("Rasedi: Transaction not found for reference %s" % reference)
        
        return tx

    def _process_notification_data(self, notification_data):
        """ Process the transaction update. """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'rasedi':
            return

        status = notification_data.get('status')
        # Map statuses
        # SUCCESS, PENDING, CANCELED, FAILED
        
        if status == 'PAID':
            _logger.info("Rasedi: Setting transaction %s to DONE (PAID)", self.reference)
            self._set_done()
        elif status == 'CANCELED':
            _logger.info("Rasedi: Setting transaction %s to CANCELED", self.reference)
            self._set_canceled()
        elif status == 'FAILED':
             _logger.info("Rasedi: Setting transaction %s to ERROR (FAILED)", self.reference)
             self._set_error("Payment Failed")
        elif status == 'TIMED_OUT':
             _logger.info("Rasedi: Setting transaction %s to ERROR (TIMED_OUT)", self.reference)
             self._set_error("Payment Timed Out")
        elif status == 'PENDING':
            _logger.info("Rasedi: Setting transaction %s to PENDING", self.reference)
            self._set_pending()
        else:
            # Fallback or log unexpected status
            _logger.warning("Rasedi: Received unknown status %s for tx %s", status, self.reference)
            self._set_error("Unknown Status: %s" % status)
