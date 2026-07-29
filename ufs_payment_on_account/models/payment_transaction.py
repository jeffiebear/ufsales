# -*- coding: utf-8 -*-
"""
Confirm the sales order when a net-terms customer checks out.

THE BUG THIS FIXES
==================
This module was written on the assumption, stated in its own manifest,
that the stock custom-provider flow goes "transaction set to pending ->
order confirmed". It does not. Odoo confirms an order from a payment
transaction only when that transaction reaches ``authorized`` or
``done``. ``payment_custom`` always lands on ``pending``
(``payment_custom/models/payment_transaction.py::_apply_updates`` calls
``_set_pending()`` for every provider whose code is ``custom``), and the
pending branch of ``sale/models/payment_transaction.py::_post_process``
only moves the quotation from ``draft`` to ``sent``:

    for pending_tx in self.filtered(lambda tx: tx.state == 'pending'):
        ...
        sales_orders.filtered(
            lambda so: so.state == 'draft'
        ).with_context(tracking_disable=True).action_quotation_sent()
        ...
        sales_orders._send_payment_succeeded_for_order_mail()

So a net-terms customer who completed checkout left an unconfirmed
quotation behind, and two visible problems followed from it:

1. The customer was emailed that their order "is pending, it will be
   confirmed when the payment is received", which is exactly wrong for
   someone whose account terms mean they are invoiced later. That
   wording is the pending branch of the order confirmation template,
   selected because the transaction was still pending.

2. ``date_order`` is stamped when the cart is first created and is only
   re-stamped by ``action_confirm``. An order that never confirmed kept
   the date the customer first added an item, so an order submitted
   weeks later sorted to the bottom of the quotation list and was
   missed.

WHY NOT JUST MARK THE TRANSACTION DONE
======================================
Because no money has changed hands. ``account_payment``'s
``_post_process`` reacts to ``done`` by posting the draft invoices and
calling ``_create_payment()``, which would record a customer payment
that does not exist and post revenue as collected. Net terms means the
invoice is the payment instrument and cash arrives later, so the
transaction genuinely is pending. The order is what should move, not the
transaction.

HOW THIS WORKS
==============
We confirm the order *before* delegating to ``super()``. Ordering is
deliberate: the stock pending branch above acts on orders still in
``draft`` or ``sent``, so by the time it runs there is nothing left for
it to pick up. That suppresses the "payment succeeded but your order is
not confirmed yet" email, which would otherwise arrive alongside the
real confirmation email and reintroduce the confusion we are removing.
Setting ``order.reference`` further down that same branch is not
filtered by state and still happens.

Confirmation is delegated to ``_check_amount_and_confirm_order`` rather
than calling ``action_confirm`` directly, so we inherit its guards: it
ignores transactions linked to anything other than exactly one order,
it re-checks ``_is_confirmation_amount_reached``, and it confirms with
``send_email=True`` so the customer gets the ordinary order
confirmation. With ``require_payment`` off, the required prepayment
amount is 0, so a net-terms order clears that check.

Re-entry is safe. ``_check_amount_and_confirm_order`` only looks at
orders in ``draft`` or ``sent``, so a transaction post-processed twice
(the retry cron re-runs anything not yet flagged) cannot confirm the
same order twice.
"""
from odoo import models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        """Override of `payment` to confirm net-terms orders on checkout.

        Runs before the standard post-processing so the stock pending
        branch finds no unconfirmed order to email about.
        """
        pay_on_account_txs = self.filtered(
            lambda tx: (
                tx.state == 'pending'
                # Validation transactions carry no order to confirm.
                and tx.operation != 'validation'
                and tx.provider_id.code == 'custom'
                and tx.provider_id.custom_mode == 'pay_on_account'
            )
        )
        if pay_on_account_txs:
            pay_on_account_txs._check_amount_and_confirm_order()
        super()._post_process()
