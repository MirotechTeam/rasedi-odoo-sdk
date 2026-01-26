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

    def _create_payment(self, **extra_create_values):
        """ Override to ensure payment method line exists before creating payment. """
        _logger.info(f"Rasedi: _create_payment called for tx {self.reference}")
        if self.provider_code == 'rasedi':
            self._ensure_rasedi_payment_method_line()
        return super()._create_payment(**extra_create_values)

    def _ensure_rasedi_payment_method_line(self):
        """ Check if the journal has the Rasedi payment method line, create if missing. """
        # Only simple logging to avoid spam
        # Use sudo() for all setup checks as Public user cannot read/write these settings
        
        rasedi_provider = self.provider_id
        if not rasedi_provider:
             return

        # Find 'electronic' method
        payment_method = self.env.ref('account.account_payment_method_electronic_in', raise_if_not_found=False)
        if not payment_method:
             payment_method = self.env.ref('account.account_payment_method_manual_in', raise_if_not_found=False)
        
        if not payment_method:
            _logger.warning("Rasedi: No electronic/manual payment method found.")
            return

        # Search journals with sudo
        bank_journals = self.env['account.journal'].sudo().search([('type', '=', 'bank')])
        _logger.info(f"Rasedi: Checking {len(bank_journals)} bank journals for configuration.")
        
        for journal in bank_journals:
             # Check and fix with sudo
             existing = self.env['account.payment.method.line'].sudo().search([
                ('journal_id', '=', journal.id),
                ('payment_provider_id', '=', rasedi_provider.id)
            ])
             if not existing:
                _logger.info(f"Rasedi Self-Healing: Creating missing payment method line for journal {journal.name}")
                try:
                    self.env['account.payment.method.line'].sudo().create({
                        'name': 'Rasedi',
                        'journal_id': journal.id,
                        'payment_method_id': payment_method.id,
                        'payment_provider_id': rasedi_provider.id,
                    })
                    _logger.info("Rasedi: Created line successfully.")
                except Exception as e:
                     _logger.error(f"Rasedi Self-Healing failed for journal {journal.name}: {e}")

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return the values for Rasedi payment. """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'rasedi':
            return res

        # Determine Environment URL and Relative Path
        if self.provider_id.state == 'enabled':
            api_url = 'https://stage.api.rasedi.com/v1/payment/rest/live/create'
            relative_path = "/v1/payment/rest/live/create"
        else:
            api_url = 'https://stage.api.rasedi.com/v1/payment/rest/test/create'
            relative_path = "/v1/payment/rest/test/create"
        
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
        
        # relative_path is set above
        
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

    def _rasedi_fetch_transaction_status(self):
        """ Fetch the transaction status from Rasedi API. """
        self.ensure_one()
        if self.provider_code != 'rasedi':
            return
        
        # Determine URL
        if self.provider_id.state == 'enabled':
            base_url = 'https://stage.api.rasedi.com/v1/payment/rest/live'
            relative_base = "/v1/payment/rest/live"
        else:
            base_url = 'https://stage.api.rasedi.com/v1/payment/rest/test'
            relative_base = "/v1/payment/rest/test"

        # Endpoint
        # referenceCode from Rasedi is stored in provider_reference
        if not self.provider_reference:
            _logger.warning("Rasedi: No provider reference to check status for tx %s", self.reference)
            return
            
        endpoint = f"/status/{self.provider_reference}"
        url = f"{base_url}{endpoint}"
        relative_path = f"{relative_base}{endpoint}"

        # Signing (GET request)
        secret_key = self.provider_id.rasedi_secret_key
        private_key = self.provider_id.rasedi_private_key
        
        raw_sign = f"GET || {secret_key} || {relative_path}"
        signature = self._rasedi_sign(raw_sign, private_key)

        headers = {
            'Content-Type': 'application/json',
            'x-id': secret_key,
            'x-signature': signature
        }
        
        try:
            _logger.info("Rasedi: Fetching status for %s from %s", self.reference, url)
            req = requests.get(url, headers=headers, timeout=10)
            req.raise_for_status()
            data = req.json()
            
            _logger.info("Rasedi: Status response: %s", json.dumps(data))
            
            # The structure based on SDK seems to return body directly or wrapped?
            # client.py: resp["body"] -> IPaymentDetailsResponseBody
            # The API returns the details directly usually. 
            # Looking at client.py: 
            # resp = await self.__call(...) which returns body.
            # So 'data' here is the payment details object.
            
            self._process_notification_data(data)
            
        except Exception as e:
            _logger.error("Rasedi: Failed to fetch status: %s", e)
