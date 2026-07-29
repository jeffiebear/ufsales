# -*- coding: utf-8 -*-
{
    'name': 'UFS Pay on Account',
    'version': '19.0.1.3.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Net-terms "Pay on Account" checkout option for approved wholesale customers.',
    'description': """
UFS Pay on Account
==================

A dedicated custom payment provider that lets net-terms wholesale
customers place an order online without paying — the order is confirmed
with the payment left *pending*, and UFS bills the customer per their
account's payment terms.

It rides Odoo's built-in custom-provider flow (the same engine wire
transfer uses, code='custom' -> transaction set to pending) but with its
own ``custom_mode = 'pay_on_account'`` so it carries no Cash-on-Delivery
restrictions or Wire-Transfer bank-detail branding.

The transaction stays *pending* on purpose: with net terms no money has
moved, and marking it done would make Odoo post a customer payment that
does not exist. Stock Odoo confirms an order only on an authorized or
done transaction, so on its own that would leave every net-terms
checkout sitting as an unconfirmed quotation. ``payment_transaction.py``
closes that gap by confirming the order itself while leaving the
transaction pending. See that file for the full reasoning.

Visibility is gated by ``ufs_requires_payment_terms`` (from
ufs_wholesale): the option only appears at checkout for customers who
have payment terms set. Everyone else sees credit card (Stripe) only.
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    # 'sale' is explicit even though ufs_wholesale pulls it in through
    # website_sale: payment_transaction.py calls sale's
    # _check_amount_and_confirm_order, so the dependency is direct.
    'depends': [
        'payment_custom',
        'sale',
        'ufs_wholesale',
    ],
    'data': [
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/mail_template_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
