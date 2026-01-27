# Rasedi Payment Provider for Odoo

This module allows you to accept payments using the Rasedi Payment Gateway in Odoo 19+.

## Installation

1.  Copy the `payment_rasedi` folder into your Odoo `addons` directory (or custom addons path).
2.  Restart your Odoo server.
3.  Go to **Apps**, click "Update Apps List", and search for **Rasedi**.
4.  Click **Activate/Install**.

## Configuration

1.  Go to **Accounting / Configuration / Payment Providers**.
2.  Select **Rasedi**.
3.  Set the **State** to *Test* or *Enabled*.
4.  Enter your **Rasedi Secret Key** and **Rasedi Private Key** (PEM format).
    - *Note*: Ensure you have the `cryptography` Python library installed in your Odoo environment:
      ```bash
      pip install cryptography
      ```
5.  Save and publish the provider.

## Features

-   **Seamless Integration**: Standard Odoo Payment Provider.
-   **Security**: Uses Ed25519 signing for all requests.
-   **Operations**: Supports Payment Creation and Status Updates via Webhook.

## Directory Structure

```
payment_rasedi/
├── __init__.py
├── __manifest__.py
├── controllers/          # Webhook & Return handlers
├── data/                 # Default configuration
├── models/               # Provider & Transaction Logic
├── static/               # Assets (Icons)
└── views/                # XML Views
```

## Publishing to Odoo Apps Store

1.  **Zip the Module**: Create a zip file of the `payment_rasedi` directory.
2.  **Login**: Go to [apps.odoo.com](https://apps.odoo.com) and login.
3.  **Upload**: Navigate to "My Apps" -> "Upload".
4.  **Metadata**: Ensure `__manifest__.py` has accurate description, version, and license. Odoo Apps parses this file.
5.  **Submit**: Upload the zip file. The store will automatically scan it.

**Requirements**:
-   Python `cryptography` library.
