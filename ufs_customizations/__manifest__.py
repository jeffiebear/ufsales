# -*- coding: utf-8 -*-
{
    'name': 'UFS Customizations',
    'version': '19.0.1.0.0',
    'summary': 'Catch-all module for small UFS-specific tweaks to standard Odoo behavior.',
    'description': """
UFS Customizations
==================

A single home for small, focused customizations to standard Odoo that
don't justify a module of their own. Each tweak lives in its own file
(model + view) and is documented inline so future maintainers can see
*why* it exists, not just what it does.

Current tweaks
--------------
* **Sale order line margin column** — displays cost, margin amount, and
  margin % on each order line as a guide for staff entering manual
  quotes/orders. Internal-only: gated behind the Sales / User group so
  the values never render in the customer portal or website templates.
* **Create Customer Price Rules button** — header action on the sale
  order that snapshots each line's unit price as a Special Price rule
  in ``ufs_customer_pricing``, skipping any product that already has a
  rule for this customer. Lets admins lock in quoted prices in one
  click after hand-tuning a manual order.
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    'category': 'Tools',
    # sale_management gives us sale.order / sale.order.line and the
    # standard order form we extend. product is implicit but listed for
    # clarity since the margin computation reads product.standard_price.
    # ufs_customer_pricing supplies the ufs.price.rule model that the
    # "Create Customer Price Rules" button writes into.
    'depends': [
        'sale_management',
        'product',
        'ufs_customer_pricing',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
