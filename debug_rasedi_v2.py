from odoo import api, SUPERUSER_ID
import sys

def diagnosis(env):
    print("--- Rasedi Diagnosis V2 ---")
    
    # 1. Check Provider
    provider = env.ref('payment_rasedi.payment_provider_rasedi', raise_if_not_found=False)
    if not provider:
        print("FAIL: Provider 'payment_rasedi.payment_provider_rasedi' NOT FOUND.")
        # Try search by code
        provider = env['payment.provider'].search([('code', '=', 'rasedi')], limit=1)
        if provider:
             print(f"WARN: Provider found via search (xmlid broken?): {provider.name}")
    else:
        print(f"PASS: Provider found: {provider.name} (ID: {provider.id}) State: {provider.state}")

    if not provider:
        print("FATAL: Cannot proceed without provider.")
        return

    # 2. Check Payment Method
    # Try multiple codes used for 'Electronic' in Odoo 16
    methods = env['account.payment.method'].search([])
    
    target_method = env.ref('account.account_payment_method_electronic_in', raise_if_not_found=False) or \
                    env.ref('account.account_payment_method_manual_in', raise_if_not_found=False)
    
    if not target_method:
        print("FAIL: No target payment method (electronic/manual) found.")
    else:
        print(f"PASS: Target Method found: {target_method.name} ({target_method.code})")

    # 3. Check Journals
    journals = env['account.journal'].search([('type', '=', 'bank')])
    if not journals:
        print("FAIL: No Bank Journals found.")
    else:
        print(f"INFO: Found {len(journals)} Bank Journals: {[j.name for j in journals]}")
        
    if provider and target_method and journals:
        # 4. Check Payment Method Lines
        for journal in journals:
            lines = env['account.payment.method.line'].search([
                ('journal_id', '=', journal.id),
                ('payment_provider_id', '=', provider.id)
            ])
            if lines:
                print(f"PASS: Journal '{journal.name}' HAS Rasedi line: {[l.name for l in lines]}")
            else:
                print(f"FAIL: Journal '{journal.name}' MISSING Rasedi line.")
                
                # Attempt Fix
                print(f"FIX: Attempting to create line for '{journal.name}'...")
                try:
                    env['account.payment.method.line'].create({
                        'name': 'Rasedi',
                        'journal_id': journal.id,
                        'payment_method_id': target_method.id,
                        'payment_provider_id': provider.id,
                    })
                    print("PASS: Line Created.")
                    env.cr.commit()
                except Exception as e:
                    print(f"ERROR: Could not create line: {e}")

if __name__ == '__main__':
    diagnosis(env)
