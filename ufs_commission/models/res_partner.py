# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ufs_sales_rep_id = fields.Many2one(
        "hr.employee",
        string="Sales Rep",
        tracking=True,
        help="Employee who earns commission on this customer's orders. New "
             "orders pick it up from the company, also when the order is "
             "placed by one of its contacts.",
    )
