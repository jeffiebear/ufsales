# -*- coding: utf-8 -*-
"""
Sale order line — Fixed-Price Margin Alert.

A line is "fixed-price" when its price came from a customer Special
Price rule (i.e. a ``ufs.price.rule`` linked into the customer's
pricelist). When such a line also has a margin below the configured
threshold, the line is flagged so the salesperson sees an inline
warning and the order gets a follow-up activity on confirm.

The detection joins two pieces:

  * Odoo 19's ``sale.order.line.pricelist_item_id`` records which
    pricelist item priced the line.
  * ``ufs.price.rule.pricelist_item_id`` records the back-link from
    each rule to its mirror item.

If the line's ``pricelist_item_id`` is the mirror item of a UFS rule
whose ``rule_type == 'special'``, the line was priced by a customer
Special Price rule.
"""
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    ufs_is_fixed_price = fields.Boolean(
        string='Fixed Price',
        compute='_compute_ufs_fixed_price_alert',
        store=False,
        help="True when this line's price came from a customer "
             "Special Price rule (a ufs.price.rule with rule_type "
             "'special'). Manual price edits and bracket prices are "
             "not considered fixed-price for alerting purposes.",
    )

    ufs_margin_alert = fields.Boolean(
        string='Margin Alert',
        compute='_compute_ufs_fixed_price_alert',
        store=False,
        help="True when the line is fixed-price AND its margin % is "
             "at or below the global Fixed-Price Margin Threshold "
             "(default 18%). Drives the inline indicator on the order "
             "form and the daily digest.",
    )

    @api.depends(
        'pricelist_item_id', 'product_id',
        'ufs_margin_percent', 'price_subtotal',
        'order_id.partner_id',
    )
    def _compute_ufs_fixed_price_alert(self):
        # Resolve threshold once per recordset (config_parameter read).
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            threshold = float(
                ICP.get_param('ufs_alerts.fixed_price_margin_threshold', 18.0)
            )
        except (TypeError, ValueError):
            threshold = 18.0

        # Pre-resolve: which pricelist_items correspond to UFS Special
        # Price rules? One search per compute call instead of per line.
        items = self.mapped('pricelist_item_id').ids
        special_item_ids = set()
        if items:
            Rule = self.env['ufs.price.rule'].sudo()
            for r in Rule.search([
                ('pricelist_item_id', 'in', items),
                ('rule_type', '=', 'special'),
            ]):
                special_item_ids.add(r.pricelist_item_id.id)

        for line in self:
            is_fixed = bool(
                line.pricelist_item_id
                and line.pricelist_item_id.id in special_item_ids
            )
            line.ufs_is_fixed_price = is_fixed
            line.ufs_margin_alert = bool(
                is_fixed
                and line.price_subtotal > 0
                and line.ufs_margin_percent <= threshold
            )
