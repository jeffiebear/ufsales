# -*- coding: utf-8 -*-
"""
Alert the office when a website order is placed.

Website orders confirm on their own now (card orders when the payment is
captured, net-terms orders through ufs_payment_on_account), so nobody was
being copied on them and new orders were slipping past. This emails a
fixed office inbox, orders@ufsales.com by default, the moment a website
order is confirmed.

WHY action_confirm AND NOT ON CREATE
====================================
A website sale.order is created the instant a shopper first adds an item
to the cart, and it then sits in draft for as long as they browse.
Notifying on creation would fire on every abandoned cart. Confirmation is
the point at which a real order exists, and every route to it (card
capture, net-terms submit, or a staff member confirming a web quote)
passes through action_confirm exactly once, so this fires once per order
and never for a cart that was never completed.

The send is wrapped so a mail failure can never roll back an order
confirmation: the order matters, the courtesy email does not.
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)

NOTIFY_PARAM = 'ufs_wholesale.new_order_notify_emails'
NOTIFY_TEMPLATE = 'ufs_wholesale.mail_template_new_web_order'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        try:
            self._ufs_notify_new_web_order()
        except Exception:
            _logger.exception(
                "UFS: failed to send new website-order notification for %s",
                self.ids,
            )
        return res

    def _ufs_notify_new_web_order(self):
        """Email the configured office inbox once per confirmed website order.

        No-op when the order did not originate on the website or when no
        recipient is configured."""
        web_orders = self.sudo().filtered('website_id')
        if not web_orders:
            return
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param(NOTIFY_PARAM, '') or ''
        addrs = ",".join(a.strip() for a in raw.split(',') if a.strip())
        if not addrs:
            return
        template = self.env.ref(NOTIFY_TEMPLATE, raise_if_not_found=False)
        if not template:
            return
        for order in web_orders:
            template.sudo().send_mail(
                order.id,
                force_send=True,
                email_values={'email_to': addrs},
            )
