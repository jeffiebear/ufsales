# -*- coding: utf-8 -*-
"""
Settings panel for ufs_customizations.

Single toggle today: auto-invoice on outgoing delivery validation.
Stored as an ``ir.config_parameter`` so it survives module upgrades
and the stock.picking override reads it without instantiating a
res.config.settings record.
"""
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ufs_auto_invoice_on_delivery = fields.Boolean(
        string='Auto-invoice on Delivery',
        config_parameter='ufs_customizations.auto_invoice_on_delivery',
        default=False,
        help="When enabled, validating an outgoing delivery "
             "automatically creates, posts, and emails the customer "
             "invoice for the delivered quantities. Backordered "
             "quantities stay open and invoice when their picking "
             "validates later. Requires products to be set to "
             "'Delivered quantities' invoicing policy.",
    )
