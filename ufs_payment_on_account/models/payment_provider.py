# -*- coding: utf-8 -*-
"""
Pay-on-Account custom payment provider.

Adds a new custom_mode and tells Odoo which payment method to activate
for it. The state machine is inherited unchanged from ``payment_custom``
(everything there keys on ``provider_code == 'custom'``, not on the
mode), so selecting this provider leaves the transaction pending.

Pending alone does NOT confirm the order: stock Odoo confirms only on an
authorized or done transaction. Order confirmation for this mode is
handled in ``payment_transaction.py``.
"""
from odoo import fields, models

from odoo.addons.ufs_payment_on_account import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    custom_mode = fields.Selection(
        selection_add=[('pay_on_account', "Pay on Account")],
        ondelete={'pay_on_account': 'cascade'},
    )

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the Pay-on-Account method code
        for our mode (else defer to the standard resolution)."""
        self.ensure_one()
        if self.code == 'custom' and self.custom_mode == 'pay_on_account':
            return const.DEFAULT_PAYMENT_METHOD_CODES
        return super()._get_default_payment_method_codes()
