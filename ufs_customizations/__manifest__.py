# -*- coding: utf-8 -*-
{
    'name': 'UFS Customizations',
    'version': '19.0.1.5.0',
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
* **Margin Preset dropdown** — a Many2one dropdown on both sale order
  lines and purchase order lines, seeded with 15 / 18 / 20 / 25 / 30 /
  35 / 40 %. On SO lines it sets ``price_unit = cost / (1 - margin)``.
  On PO lines it sets the product's catalog ``list_price`` from the
  vendor cost. Admins can edit the preset list under Sales →
  Configuration → Margin Presets (or the same under Purchase).
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    'category': 'Tools',
    # sale_management + purchase give us the order/line models we extend.
    # product is implicit but listed for clarity. ufs_customer_pricing
    # supplies the ufs.price.rule model that the "Create Customer Price
    # Rules" button writes into.
    # NOTE: deliberately NOT depending on ufs_alerts even though
    # stock_picking references its margin-alert activity type. That
    # reference uses env.ref(raise_if_not_found=False) so it degrades
    # gracefully when ufs_alerts isn't installed, and ufs_alerts itself
    # depends on this module (for ufs_margin_percent) — declaring the
    # reverse here would create a dependency loop.
    'depends': [
        'sale_management',
        'purchase',
        'stock',
        'account',
        'product',
        'ufs_customer_pricing',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ufs_margin_preset_data.xml',
        'data/ir_cron_data.xml',
        'views/ufs_margin_preset_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ufs_customizations/static/src/chatter_resize/chatter_resize.js',
            'ufs_customizations/static/src/chatter_resize/chatter_resize.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
