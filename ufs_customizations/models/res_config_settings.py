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
             "validates later. Only customers WITH payment terms are "
             "invoiced; customers without terms (credit-card / prepaid) "
             "are skipped. Requires products set to 'Delivered "
             "quantities' invoicing policy.",
    )

    ufs_consolidate_draft_pos = fields.Boolean(
        string='Consolidate Draft Purchase Orders Daily',
        config_parameter='ufs_customizations.consolidate_draft_pos',
        default=False,
        help="When enabled, a nightly job merges same-vendor DRAFT "
             "purchase orders into one each (so backordered items stop "
             "creating a separate PO per item). Only draft POs that match "
             "on vendor, currency, ship-to, and terms are merged; lines "
             "are moved intact so procurement links are preserved. You "
             "can also merge on demand from the Purchase Orders list "
             "Action menu.",
    )
