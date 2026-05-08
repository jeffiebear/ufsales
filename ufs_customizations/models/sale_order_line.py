# -*- coding: utf-8 -*-
"""
Sale order line — margin guide fields.

Adds three computed, non-stored fields to ``sale.order.line`` that
surface profit margin while staff are building a manual quote/order:

    ufs_cost_unit       — unit cost (product.standard_price), converted
                          into the order's currency so the math lines up
                          with price_unit/price_subtotal.
    ufs_margin_amount   — price_subtotal - (cost_unit * qty)
    ufs_margin_percent  — margin_amount / price_subtotal * 100

These are intentionally *not stored*: they're a live decision aid, not
a reporting metric. If we later want margin reports we should either
flip ``store=True`` or lean on Odoo's official ``sale_margin`` module,
which persists per-line margin for reporting.

The fields are only meaningful to internal sales staff. View visibility
is restricted via ``groups="sales_team.group_sale_salesman"`` on the
view side, so portal/website renders never include them.
"""
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Unit cost expressed in the *order* currency. We pull
    # product.standard_price (always in the product's company currency)
    # and convert at the order date so the margin matches what the
    # customer is being charged.
    ufs_cost_unit = fields.Monetary(
        string='Cost',
        compute='_compute_ufs_margin',
        currency_field='currency_id',
        groups='sales_team.group_sale_salesman',
        help="Product cost (standard_price) at the time the line is "
             "viewed, converted into the order's currency. Live value "
             "— not snapshotted on the order.",
    )

    ufs_margin_amount = fields.Monetary(
        string='Margin',
        compute='_compute_ufs_margin',
        currency_field='currency_id',
        groups='sales_team.group_sale_salesman',
        help="price_subtotal − (cost × quantity). Excludes taxes and "
             "uses the line's after-discount subtotal.",
    )

    ufs_margin_percent = fields.Float(
        string='Margin %',
        compute='_compute_ufs_margin',
        digits=(16, 2),
        groups='sales_team.group_sale_salesman',
        help="Margin as a percentage of price_subtotal. Returns 0 when "
             "the subtotal is zero (free lines, 100%-discount lines).",
    )

    @api.depends(
        'product_id', 'product_id.standard_price',
        'product_uom_qty', 'price_subtotal',
        'order_id.currency_id', 'order_id.company_id', 'order_id.date_order',
    )
    def _compute_ufs_margin(self):
        for line in self:
            product = line.product_id
            order = line.order_id
            # Section / note lines have no product — leave fields blank.
            if not product or not order:
                line.ufs_cost_unit = 0.0
                line.ufs_margin_amount = 0.0
                line.ufs_margin_percent = 0.0
                continue

            # Convert product cost (in product's company currency) into
            # the order's currency. _convert is a no-op when both
            # currencies match, which is the common case.
            product_currency = product.cost_currency_id or product.company_id.currency_id
            order_currency = order.currency_id or product_currency
            cost_unit = product_currency._convert(
                product.standard_price,
                order_currency,
                order.company_id or self.env.company,
                order.date_order or fields.Date.context_today(line),
                round=False,
            ) if product_currency and order_currency else product.standard_price

            margin_amount = line.price_subtotal - (cost_unit * line.product_uom_qty)
            # Guard against div-by-zero on $0 / 100%-discount lines.
            margin_percent = (
                (margin_amount / line.price_subtotal) * 100.0
                if line.price_subtotal else 0.0
            )

            line.ufs_cost_unit = cost_unit
            line.ufs_margin_amount = margin_amount
            line.ufs_margin_percent = margin_percent
