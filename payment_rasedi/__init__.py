from . import controllers
from . import models

from odoo import api, SUPERUSER_ID

def uninstall_hook(env):
    # Retrieve the payment providers
    providers = env['payment.provider'].search([('code', '=', 'rasedi')])
    # Reset the redirect form view to the default one to avoid dependency issues on uninstall
    # The default view is 'payment.redirect_form'
    default_view = env.ref('payment.redirect_form', raise_if_not_found=False)
    if default_view:
        providers.write({'redirect_form_view_id': default_view.id})

