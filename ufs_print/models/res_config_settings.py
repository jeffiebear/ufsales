# -*- coding: utf-8 -*-
"""
Settings for the direct-print relay.

All values land in ir.config_parameter so the wizard can read them
without instantiating a settings record, and so they can be scripted
from the shell during setup.

Keys:
    ufs_print.enabled         '1' / '0'
    ufs_print.webhook_url      https://parameter-api.com/ufs/print-webhook.php
    ufs_print.shared_secret    matches X-Print-Secret on the relay
    ufs_print.default_copies   integer, default 1
    ufs_print.timeout          seconds, default 20
"""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ufs_print_enabled = fields.Boolean(
        string='Enable Konica Printing',
        config_parameter='ufs_print.enabled',
        help="Master switch. When off, the Print to Konica buttons "
             "raise a friendly 'printing is turned off' message instead "
             "of contacting the relay.",
    )
    ufs_print_webhook_url = fields.Char(
        string='Print Relay URL',
        config_parameter='ufs_print.webhook_url',
        help="The print-relay webhook endpoint, e.g. "
             "https://parameter-api.com/ufs/print-webhook.php",
    )
    ufs_print_shared_secret = fields.Char(
        string='Shared Secret',
        config_parameter='ufs_print.shared_secret',
        help="Sent as the X-Print-Secret header. Must match the secret "
             "configured on the relay.",
    )
    ufs_print_default_copies = fields.Integer(
        string='Default Copies',
        config_parameter='ufs_print.default_copies',
        default=1,
    )
    ufs_print_timeout = fields.Integer(
        string='Relay Timeout (seconds)',
        config_parameter='ufs_print.timeout',
        default=20,
    )
