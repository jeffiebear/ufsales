# -*- coding: utf-8 -*-
"""
Account move (invoice) — auto-email helper.

Standalone helper used by ``stock_picking._ufs_create_delivery_invoice``
so the auto-invoice flow has a single place to find the right email
template and send it. Splitting it out keeps the picking override
focused on workflow and lets us test the email path in isolation.
"""
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _ufs_send_invoice_email(self):
        """Send this invoice using the standard customer-invoice email
        template. Caller wraps this in try/except — we raise on any
        problem so the auto-invoice flow can decide whether to block,
        log an activity, etc.
        """
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_(
                "Cannot email a non-posted invoice (%s, state=%s)."
            ) % (self.name, self.state))

        template = self.env.ref(
            'account.email_template_edi_invoice',
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_(
                "Standard invoice email template not found. Cannot "
                "send invoice %s automatically."
            ) % self.name)

        if not self.partner_id.email:
            raise UserError(_(
                "Customer %s has no email on file. Cannot send invoice "
                "%s automatically — fill in the email or send manually."
            ) % (self.partner_id.display_name, self.name))

        # send_mail with force_send=True bypasses the queue. We want
        # invoice emails out the door immediately, not at next mail-
        # cron tick.
        template.send_mail(self.id, force_send=True)
        _logger.info(
            "ufs auto-invoice: emailed invoice %s to %s",
            self.name, self.partner_id.email,
        )
        # Mark as sent for the Odoo UI flag.
        self.is_move_sent = True
