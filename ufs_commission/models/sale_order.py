# -*- coding: utf-8 -*-
"""
Sales rep and commission on the sale order.

The rep comes from the customer (its company, so an order placed by a
contact still finds it) and stays editable on the order. The rate is
copied from the employee when the rep is set, so a later rate change
does not rewrite history. The amount follows the order's margin, which
sale_margin keeps up to date as lines change.

Reports count an order once it is confirmed (state 'sale'), in the
month of its order date. Cancelled orders drop out.
"""
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ufs_sales_rep_id = fields.Many2one(
        "hr.employee",
        string="Sales Rep",
        compute="_compute_ufs_sales_rep_id",
        store=True, readonly=False, precompute=True,
        tracking=True, index=True,
        help="Employee who earns commission on this order. Defaults from the customer.",
    )
    ufs_commission_rate = fields.Float(
        string="Commission %",
        compute="_compute_ufs_commission_rate",
        store=True, readonly=False,
        help="Percent of margin paid on this order. Copied from the sales rep when the rep is set.",
    )
    ufs_commission_amount = fields.Monetary(
        string="Commission",
        compute="_compute_ufs_commission_amount",
        store=True,
        help="Margin x Commission %.",
    )

    @api.depends("partner_id")
    def _compute_ufs_sales_rep_id(self):
        for order in self:
            order.ufs_sales_rep_id = order.partner_id.commercial_partner_id.ufs_sales_rep_id

    @api.depends("ufs_sales_rep_id")
    def _compute_ufs_commission_rate(self):
        for order in self:
            order.ufs_commission_rate = order.ufs_sales_rep_id.sudo().ufs_commission_rate

    @api.depends("margin", "ufs_commission_rate", "ufs_sales_rep_id")
    def _compute_ufs_commission_amount(self):
        for order in self:
            amount = order.margin * order.ufs_commission_rate / 100.0 if order.ufs_sales_rep_id else 0.0
            order.ufs_commission_amount = order.currency_id.round(amount) if order.currency_id else amount
