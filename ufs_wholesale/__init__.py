# -*- coding: utf-8 -*-

import logging

from . import controllers
from . import models

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    """Undo a mistaken Cash-on-Delivery repurpose.

    Net-terms "Pay on Account" is its own dedicated provider now (see the
    ufs_payment_on_account module). If COD was previously renamed/flagged
    as a stop-gap, reset it here so it stops competing or appearing —
    COD can't reliably show at normal web checkout anyway. Idempotent.
    """
    Provider = env['payment.provider'].sudo()
    cod = Provider.search([
        ('code', '=', 'custom'),
        ('custom_mode', '=', 'cash_on_delivery'),
        ('ufs_requires_payment_terms', '=', True),
    ])
    for prov in cod:
        vals = {'ufs_requires_payment_terms': False}
        if 'is_published' in prov._fields:
            vals['is_published'] = False
        if prov.name and 'Pay on Account' in prov.name:
            vals['name'] = 'Cash on Delivery'
        prov.write(vals)
        _logger.info(
            "ufs_wholesale: reset mistaken COD provider id=%s "
            "(unflagged + unpublished).", prov.id,
        )
