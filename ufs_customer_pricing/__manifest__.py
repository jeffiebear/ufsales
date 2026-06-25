# -*- coding: utf-8 -*-
{
    'name': 'UFS Customer Pricing',
    'version': '19.0.1.4.0',
    'summary': 'Customer-specific pricing rules migrated from STEP1, with auto-sync to Odoo pricelists.',
    'description': """
UFS Customer Pricing
====================

Maintains rich customer/product pricing rules — modelled after STEP1's
CustomerPriceRule structure — and keeps standard Odoo pricelists in sync
so quotes, sales orders, and POS pick up the right price natively.

Key features
------------
* Rule types: Special (fixed price), Profit Margin, Cost Markup, Quantity
  Bracket, Customer Default, List Price.
* Per-customer pricelist auto-created and maintained.
* Margin / markup rules use Odoo's formula pricelist on cost — as
  ``standard_price`` changes, the selling price recomputes.
* CSV import wizard pre-shaped to the STEP1 export format.
* Three management surfaces: a tab on the customer form, a tab on the
  product form, and a dedicated Customer Price Rules menu.
""",
    'author': 'Unlimited Florida Sales (UFS)',
    'website': 'https://www.unlimitedfloridasales.com',
    'license': 'LGPL-3',
    'category': 'Sales/Sales',
    'depends': [
        'sale_management',
        'product',
    ],
    'data': [
        'security/ufs_customer_pricing_security.xml',
        'security/ir.model.access.csv',
        'views/ufs_price_rule_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'wizards/ufs_price_rule_import_views.xml',
        'wizards/ufs_pricing_maintenance_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
