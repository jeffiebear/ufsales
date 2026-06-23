# -*- coding: utf-8 -*-
"""
Gate "pay on account / net terms" checkout to customers with terms.

Adds a flag on payment.provider. Any provider flagged
``ufs_requires_payment_terms`` is offered at WEBSITE CHECKOUT only to
customers whose account has payment terms (a net-terms account).
Unflagged providers (e.g. Stripe / credit card) stay available to
everyone — so a walk-up / prepaid customer's only option is the card,
while approved net-terms customers additionally see "Pay on Account."

Implementation: override ``payment.provider._get_compatible_providers``
(the method website checkout uses to list providers) and drop flagged
providers when the checkout's customer has no payment term. The Odoo 19
signature is ``(*args, sale_order_id=None, ...)``; we resolve the
customer from an explicit partner_id when present, else from the cart.
"""
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    ufs_requires_payment_terms = fields.Boolean(
        string="Requires Payment Terms",
        help="If set, this payment option appears at website checkout "
             "ONLY for customers who have payment terms configured "
             "(net-terms accounts). Tick this on a 'Pay on Account / "
             "Net Terms' provider so credit-card / prepaid customers "
             "never see it.",
    )

    def _get_compatible_providers(self, *args, sale_order_id=None, **kwargs):
        providers = super()._get_compatible_providers(
            *args, sale_order_id=sale_order_id, **kwargs
        )
        # If nothing is flagged, there is nothing to filter — cheap exit.
        if not any(p.ufs_requires_payment_terms for p in providers):
            return providers

        # Resolve the checkout customer from whatever the caller provided:
        # an explicit partner_id (kwarg or legacy positional), else the cart.
        partner = self.env['res.partner']
        partner_id = kwargs.get('partner_id')
        if not partner_id and len(args) >= 2 and isinstance(args[1], int):
            # Legacy positional signature (company_id, partner_id, amount, ...)
            partner_id = args[1]
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
        elif sale_order_id:
            partner = self.env['sale.order'].browse(sale_order_id).partner_id

        if not partner:
            return providers

        # Net terms can sit on the contact or its commercial (company) partner.
        term = partner.property_payment_term_id \
            or partner.commercial_partner_id.property_payment_term_id
        if not term:
            providers = providers.filtered(
                lambda p: not p.ufs_requires_payment_terms
            )
        return providers
