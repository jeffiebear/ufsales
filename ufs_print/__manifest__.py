# -*- coding: utf-8 -*-
{
    'name': 'UFS Direct Print',
    'version': '19.0.1.1.0',
    'summary': 'One-click "Print to Konica" on orders, invoices, deliveries, and POs via a print-relay webhook.',
    'description': """
UFS Direct Print
================

Adds a "Print to Konica" button to sale orders, customer invoices,
delivery slips, and purchase orders. Clicking it renders the standard
report to PDF and POSTs it (base64, JSON) to a configurable print-relay
webhook with a shared-secret header — the same pattern used for the
Jalaram Produce WooCommerce store.

The relay (CUPS on the Parameter VPS) handles the actual printing,
including copies and single/double-sided, so this module is fully
decoupled from the printer hardware and network. Point it at the
webhook URL + secret in Settings → UFS Printing and turn it on.

A small popup exposes per-print controls (copies + double-sided), and
every print attempt is logged to the document's chatter with the
relay's response.
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    'category': 'Tools',
    'depends': [
        'sale_management',
        'account',
        'stock',
        'purchase',
        'mail',
        'account_check_printing',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/ufs_print_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/print_buttons.xml',
        'views/check_print_button.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
