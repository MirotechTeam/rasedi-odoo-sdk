{
    'name': 'Rasedi Payment Provider',
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': 'A payment provider to accept payments via Rasedi.',
    'author': 'Rasedi',
    'website': 'https://rasedi.com',
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',
    ],
    'images': ['static/description/main_screenshot.png'],
    'application': False,
    'license': 'LGPL-3',
}
