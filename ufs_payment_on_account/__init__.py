# -*- coding: utf-8 -*-

from . import models

from odoo.addons.payment import setup_provider, reset_payment_provider


def post_init_hook(env):
    # Activate the pay_on_account payment method and finish wiring the
    # provider, mirroring payment_custom's own post_init_hook for
    # wire_transfer.
    setup_provider(env, 'custom', custom_mode='pay_on_account')


def uninstall_hook(env):
    reset_payment_provider(env, 'custom', custom_mode='pay_on_account')
