# -*- coding: utf-8 -*-

import logging

from . import controllers
from . import models

_logger = logging.getLogger(__name__)

_ON_ACCOUNT_MSG = (
    "<p>Thank you — your order is confirmed.</p>"
    "<p>You will be invoiced according to your account's payment terms. "
    "No payment is required online.</p>"
)


def post_init_hook(env):
    """Provision the "Pay on Account (Net Terms)" checkout option in code.

    We ride Odoo's proven custom WIRE-TRANSFER provider (offline payment:
    it confirms the order without capturing money, which is exactly the
    net-terms behavior) rather than a hand-built provider, and we steer
    customers away from the Cash-on-Delivery provider which Odoo restricts
    from normal web checkout.

    Idempotent. Leaves env-specific bits (enabling, the payment journal,
    website publishing) to the admin — those can't be set reliably from a
    data hook.
    """
    Provider = env['payment.provider'].sudo()

    # 1) Repurpose the wire-transfer provider as "Pay on Account".
    wire = Provider.search(
        [('code', '=', 'custom'), ('custom_mode', '=', 'wire_transfer')],
        limit=1,
    )
    if wire:
        vals = {
            'name': 'Pay on Account (Net Terms)',
            'ufs_requires_payment_terms': True,
        }
        if 'pending_msg' in wire._fields:
            vals['pending_msg'] = _ON_ACCOUNT_MSG
        wire.write(vals)
        _logger.info(
            "ufs_wholesale: configured wire-transfer provider id=%s as "
            "'Pay on Account (Net Terms)' (flagged net-terms-only). "
            "Admin must enable it, set its payment journal, and publish it.",
            wire.id,
        )
    else:
        _logger.warning(
            "ufs_wholesale: no wire-transfer custom provider found to use "
            "for Pay on Account. Create one (Payment Providers) or tell "
            "Parameter."
        )

    # 2) Undo a mistaken Cash-on-Delivery repurpose: unflag + unpublish it
    #    so it stops competing/appearing. COD can't reliably show at web
    #    checkout anyway.
    cod = Provider.search(
        [('code', '=', 'custom'), ('custom_mode', '=', 'cash_on_delivery'),
         ('ufs_requires_payment_terms', '=', True)],
    )
    for prov in cod:
        cod_vals = {'ufs_requires_payment_terms': False}
        if 'is_published' in prov._fields:
            cod_vals['is_published'] = False
        # Only rename it back if it was renamed to our label.
        if prov.name and 'Pay on Account' in prov.name:
            cod_vals['name'] = 'Cash on Delivery'
        prov.write(cod_vals)
        _logger.info(
            "ufs_wholesale: reset mistaken COD provider id=%s "
            "(unflagged + unpublished).", prov.id,
        )
