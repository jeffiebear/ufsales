# -*- coding: utf-8 -*-
{
    'name': 'UFS Sales Rep Commissions',
    'version': '19.0.1.0.0',
    'summary': 'Commission on margin for sales reps who are employees, not Odoo users.',
    'description': """
UFS Sales Rep Commissions
=========================

Odoo's Commission app only pays internal users, and every internal user
is a paid seat. UFS's outside salesman never logs in, so this module
tracks his commission against an **employee** record instead.

* **Sales Rep on the customer.** A customer can be assigned to an
  employee. New orders for that customer pick the rep up automatically;
  it can be changed on any single order.
* **Commission rate on the employee** (percent of margin).
* **Commission on confirmed orders.** Each order stores the rep's rate
  at the time and the commission amount (margin x rate). Margin is the
  sale_margin figure: sales minus product cost.
* **Sales > Reporting > Commissions**: orders, margin and commission by
  rep and month.
* **Sales > Reporting > Commission Statement**: a printable statement
  for one rep and one period.

Nothing here posts accounting entries; it is reporting only.
""",
    'author': 'Parameter',
    'website': 'https://parameterllc.com/',
    'license': 'LGPL-3',
    'category': 'Sales',
    'depends': [
        'sale_management',
        # margin on sale.order
        'sale_margin',
        # hr.employee is the sales rep
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/commission_statement_report.xml',
        'wizard/ufs_commission_statement_views.xml',
        'views/hr_employee_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/commission_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
