# -*- coding: utf-8 -*-
{
    'name': 'UFS Step1 Invoice History',
    'version': '19.0.1.0.0',
    'summary': 'Read-only archive of the Step1 customer invoice history (pre-July 2026), for lookup and statements.',
    'description': """
UFS Step1 Invoice History
=========================

Reference archive of every customer invoice and credit memo from the
legacy Step1 system (2006 through the June 30, 2026 cutover). The
records are **not** accounting entries: they post nothing, touch no
journal, and never appear in Odoo's financial reports. They exist so
staff can look up an old invoice without opening Step1, and so a
customer statement can show Step1 history next to live Odoo invoices.

* One record per Step1 document (invoice, credit memo, counter sale),
  header level only. Line detail stays in Step1.
* Linked to the Odoo customer through the Step1 account code stored in
  the partner's Reference field. Unmatched records keep the Step1
  customer name so nothing is lost.
* Loaded once from the Step1 export by script; users cannot create or
  edit records. Accounting managers may delete and reload.
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/ufs_step1_invoice_views.xml',
        'views/res_partner_views.xml',
        'wizard/ufs_step1_import_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
