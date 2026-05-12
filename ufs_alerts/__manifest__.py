# -*- coding: utf-8 -*-
{
    'name': 'UFS Alerts',
    'version': '19.0.1.0.0',
    'summary': 'Margin-floor and low-stock alerting for UFS workflows.',
    'description': """
UFS Alerts
==========

Two operational alert families, both driven from configurable thresholds
and surfaced consistently (in-record indicator + scheduled activity +
daily email digest).

1. **Fixed-Price Margin Alert** — flags sale order lines whose price came
   from a customer Special Price rule and whose margin sits below a
   global threshold (default 18%). Activity is scheduled on the order
   when any line is flagged; a daily digest lists every open order with
   at least one flagged line.

2. **Inventory Alert** — flags products whose on-hand quantity has fallen
   to or below their reorder threshold. Threshold is 10%% of rolling
   365-day confirmed sales volume by default, with an optional fixed
   per-product override. Products with zero sales history are skipped
   (no false alerts on brand-new SKUs).
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    'category': 'Tools',
    'depends': [
        'sale_management',
        'stock',
        'mail',
        'ufs_customer_pricing',
        'ufs_customizations',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_activity_data.xml',
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/product_template_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
