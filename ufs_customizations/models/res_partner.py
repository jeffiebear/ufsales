# -*- coding: utf-8 -*-
"""
Per-customer delivery instructions that print on their pick and delivery
tickets.

Staff can enter standing instructions once on the customer (gate code, dock
hours, call-ahead, etc.) and they print automatically on every transfer for
that customer, instead of being retyped on each order. Rendered on the
Delivery Slip and Picking Operations reports (see
views/stock_delivery_instructions_reports.xml).

Author: Parameter (https://parameterllc.com/)
"""
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ufs_delivery_instructions = fields.Text(
        string="Delivery Instructions",
        help="Standing delivery instructions for this customer. Printed "
             "automatically on every pick and delivery ticket for them "
             "(e.g. gate code, dock hours, call ahead). Enter once here "
             "instead of retyping on each order.",
    )
