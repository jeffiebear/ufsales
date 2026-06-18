# -*- coding: utf-8 -*-
"""
Purchase order line — margin preset dropdown.

When a buyer enters a vendor cost on a PO line and picks a margin
preset, the *product's catalog list price* (``product.template.list_price``)
is recomputed to:

    list_price = price_unit / (1 - margin_pct / 100)

This is the natural buyer workflow: "we're picking this up at $X from
the vendor, set the sell price for everyone going forward." The change
applies to every future quote of that product to every customer, unless
they have a Special Price rule that overrides it.

Sale-order-level overrides (single quote, specific customer) live on
sale.order.line and don't touch the catalog. Same preset model, two
target fields.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    ufs_margin_preset_id = fields.Many2one(
        'ufs.margin.preset',
        string='Margin Preset',
        ondelete='restrict',
        groups='purchase.group_purchase_user',
        help="Pick a margin tier to recompute this product's catalog "
             "sell price (list_price) based on the vendor cost on this "
             "line. Applies to all future quotes of this product. "
             "Customer Special Price rules continue to override.",
    )

    @api.onchange('ufs_margin_preset_id')
    def _onchange_ufs_margin_preset(self):
        """Recompute product.template.list_price from this line's cost.

        Writes through sudo() because purchase users typically don't
        have direct write access on product.template. We log every
        write so admins can audit "where did this price come from"
        retroactively.
        """
        for line in self:
            preset = line.ufs_margin_preset_id
            if not preset or not line.product_id or not line.price_unit:
                continue
            new_list_price = preset.apply_to_cost(line.price_unit)
            if new_list_price <= 0:
                continue
            template = line.product_id.product_tmpl_id.sudo()
            old_price = template.list_price
            if abs(old_price - new_list_price) < 0.005:
                continue
            template.list_price = new_list_price
            _logger.info(
                "ufs_margin_preset: PO line %s set %s.list_price %.2f -> %.2f "
                "(cost %.2f, preset %s%%)",
                line.id or 'new',
                template.display_name,
                old_price,
                new_list_price,
                line.price_unit,
                preset.margin_pct,
            )
