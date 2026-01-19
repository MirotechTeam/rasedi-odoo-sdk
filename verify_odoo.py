
import requests
import json
import base64
import sys

# Configuration (Same keys as before)
SECRET_KEY = "live_laisxVjnNnoY1w5mwWP6YwzfPg_zmu2BnWnJH1uCOzOGcAflAYShdjVPuDAG10DLSEpTOlsOopiyTJHJjO4fbqqU"
PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEID2nK2pCcGSbtS+U9jc2SCYxHWOo1eA4IR97bdif4+rx
-----END PRIVATE KEY-----"""

API_URL = 'https://api.pallawan.com/v1/payment/rest/live/create'
RELATIVE_PATH = '/v1/payment/rest/live/create'

def sign(raw_data, private_key_pem):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    
    priv_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'),
        password=None
    )
    signature = priv_key.sign(raw_data.encode('utf-8'))
    return base64.b64encode(signature).decode('utf-8')

def test_create_payment():
    print("--- Testing Odoo Logic (Python) ---")
    
    # Payload Construction (Matching Odoo logic)
    payload = {
        'amount': '1500',
        'title': 'Odoo Module Test',
        'description': 'Verifying Odoo Logic',
        'gateways': ["CREDIT_CARD"],
        'redirectUrl': 'https://example.com/return',
        'callbackUrl': 'https://example.com/webhook',
        'collectFeeFromCustomer': True,
        'collectCustomerEmail': True,
        'collectCustomerPhoneNumber': True
    }
    
    # Signature Generation
    raw_sign = f"POST || {SECRET_KEY} || {RELATIVE_PATH}"
    print(f"Signing: {raw_sign}")
    
    try:
        signature = sign(raw_sign, PRIVATE_KEY)
        print(f"Signature: {signature}")
    except ImportError:
        print("Error: 'cryptography' library not found. Cannot verify Ed25519.")
        sys.exit(1)
        
    headers = {
        'Content-Type': 'application/json',
        'x-id': SECRET_KEY,
        'x-signature': signature
    }
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if 200 <= response.status_code < 300:
            print("SUCCESS: Payment Created")
            return response.json()['referenceCode']
        else:
            print("FAILED: HTTP Error")
            sys.exit(1)
            
    except Exception as e:
        print(f"Exception: {e}")
        sys.exit(1)

def test_status(ref_code):
    print(f"\n--- Testing Status for {ref_code} ---")
    status_endpoint = f'/v1/payment/rest/live/status/{ref_code}'
    url = f'https://api.pallawan.com{status_endpoint}'
    
    raw_sign = f"GET || {SECRET_KEY} || {status_endpoint}"
    signature = sign(raw_sign, PRIVATE_KEY)
    
    headers = {
        'Content-Type': 'application/json',
        'x-id': SECRET_KEY,
        'x-signature': signature
    }
    
    resp = requests.get(url, headers=headers)
    print(f"Status Code: {resp.status_code}")
    print(f"Body: {resp.text}")
    
    if resp.status_code == 200:
         print("SUCCESS: Status Verified")
    else:
         print("FAILED: Status Check")
         sys.exit(1)

def test_cancel(ref_code):
    print(f"\n--- Testing Cancel for {ref_code} ---")
    cancel_endpoint = f'/v1/payment/rest/live/cancel/{ref_code}'
    url = f'https://api.pallawan.com{cancel_endpoint}'
    
    raw_sign = f"PATCH || {SECRET_KEY} || {cancel_endpoint}"
    signature = sign(raw_sign, PRIVATE_KEY)
    
    headers = {
        'Content-Type': 'application/json',
        'x-id': SECRET_KEY,
        'x-signature': signature
    }
    
    resp = requests.patch(url, headers=headers)
    print(f"Status Code: {resp.status_code}")
    print(f"Body: {resp.text}")
    
    if resp.status_code == 200:
         print("SUCCESS: Payment Canceled")
    else:
         print("FAILED: Cancel")
         sys.exit(1)

if __name__ == '__main__':
    ref = test_create_payment()
    if ref:
        test_status(ref)
        test_cancel(ref)
