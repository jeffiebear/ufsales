# -*- coding: utf-8 -*-
"""
Auto-invoice on outgoing-delivery validation.

When an outgoing picking is validated, automatically create, post, and
email a customer invoice for **exactly what was just delivered**.
Backordered (undelivered) quantities stay open on the sale order and
get invoiced the same way when their picking validates later.

Design choices (locked with the customer):
    * Only outgoing pickings (picking_type_id.code == 'outgoing').
    * Auto-invoice = create draft, post, send by email.
    * Failure modes BLOCK the picking validation with a human-readable
      ``UserError``. Salesperson resolves the underlying issue, re-clicks
      Validate, and the chain proceeds.
    * Open Margin Alert activity on the sale order is treated as a
      blocker for consistency: the warehouse can't ship past an
      unresolved margin alert.
    * Feature can be globally disabled in Settings → UFS Sales →
      "Auto-invoice on delivery". When off, picking validates the
      standard Odoo way and no invoice is created.

The override hooks ``button_validate`` so we intercept *before* the
backorder dialog and *after* the actual stock moves. We let the
parent do its thing first, then invoice on the resulting state.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ufs_invoiced_on_validate = fields.Boolean(
        string='Invoiced on Validate',
        copy=False, readonly=True,
        help="Set when this delivery auto-created and posted an invoice "
             "on validation. Diagnostic — read-only.",
    )

    def button_validate(self):
        # Let Odoo do its thing first. If Odoo's own validation throws
        # or returns a wizard (backorder confirm, immediate-transfer
        # wizard, etc.), we don't proceed with auto-invoice. Auto-
        # invoice only fires when the picking has actually moved to
        # 'done' as a direct result of this call.
        res = super().button_validate()
        # The standard validate returns:
        #   - True when the picking is now done
        #   - A dict ir.actions.act_window when a wizard is needed
        # We only invoice when the result is True.
        if res is not True:
            return res

        if not self._ufs_auto_invoice_enabled():
            return res

        for picking in self:
            if picking.state != 'done':
                continue
            if picking.picking_type_code != 'outgoing':
                continue
            picking._ufs_create_delivery_invoice()
        return res

    @api.model
    def _ufs_auto_invoice_enabled(self):
        ICP = self.env['ir.config_parameter'].sudo()
        # res.config.settings stores a Boolean config_parameter as the
        # string "True"/"False" (not "1"/"0"), so accept either form.
        return ICP.get_param('ufs_customizations.auto_invoice_on_delivery') in ('True', '1', 'true')

    def _ufs_create_delivery_invoice(self):
        """Create, post, and email the invoice for this picking's
        delivered quantities. Blocks (raises UserError) on any
        failure — picking validation rolls back."""
        self.ensure_one()

        # Find the originating sale order(s). Pickings can be linked to
        # SOs via the sale_id many2one set up by the procurement chain.
        order = self.sale_id
        if not order:
            # Manual delivery without an SO — nothing to invoice.
            return

        # CC-default guard: auto-invoice only net-terms customers. An order
        # with NO payment term is treated as credit-card / pay-now and must
        # NOT be auto-invoiced. Skip silently with a chatter note. Placed
        # before the margin-alert gate so CC orders are never blocked by a
        # margin alert they'll never invoice from. We read the order's
        # payment_term_id (what the invoice would actually carry), not the
        # partner default, so per-order overrides are honored.
        if not order.payment_term_id:
            order.message_post(body=_(
                "Auto-invoice skipped: no payment terms on this order "
                "(credit-card / prepaid). Delivery %s validated without "
                "creating an invoice."
            ) % self.name)
            _logger.info(
                "ufs auto-invoice: SO %s has no payment_term_id "
                "(CC/prepaid) — skipping auto-invoice for delivery %s.",
                order.name, self.name,
            )
            return

        if order.state not in ('sale', 'done'):
            raise UserError(_(
                "Auto-invoice: Sale order %s is in state '%s'. Confirm "
                "the order before validating the delivery."
            ) % (order.name, order.state))

        # Margin-alert gate (mirrors the ufs_alerts module's flagging).
        margin_alert_type = self.env.ref(
            'ufs_alerts.mail_activity_data_margin_alert',
            raise_if_not_found=False,
        )
        if margin_alert_type:
            open_alert = self.env['mail.activity'].sudo().search([
                ('res_model', '=', 'sale.order'),
                ('res_id', '=', order.id),
                ('activity_type_id', '=', margin_alert_type.id),
            ], limit=1)
            if open_alert:
                raise UserError(_(
                    "Auto-invoice: Sale order %s has an open margin "
                    "alert activity. Resolve it before delivering."
                ) % order.name)

        # Sanity: there must be at least one invoiceable quantity. With
        # invoice_policy='delivery', Odoo computes qty_to_invoice from
        # the delivered stock moves automatically.
        invoiceable = order.order_line.filtered(
            lambda l: l.qty_to_invoice and l.qty_to_invoice > 0
        )
        if not invoiceable:
            _logger.info(
                "ufs auto-invoice: SO %s has no qty_to_invoice after "
                "delivery — skipping (likely services-only or zero qty).",
                order.name,
            )
            return

        # Create the invoice. final=True so down-payments / advances are
        # netted out properly on the final invoice line.
        try:
            moves = order._create_invoices(final=True)
        except Exception as exc:
            raise UserError(_(
                "Auto-invoice: failed to create the invoice for %s.\n\n"
                "Details: %s\n\n"
                "Fix the underlying issue (taxes, payment terms, "
                "fiscal position, etc.) and re-validate the delivery."
            ) % (order.name, exc)) from exc

        if not moves:
            raise UserError(_(
                "Auto-invoice: no invoice was created for %s. Check "
                "the order's invoice policy and confirmed quantities."
            ) % order.name)

        # Post. Wrapped so we surface a clean message instead of the
        # raw ORM stack.
        try:
            moves.action_post()
        except Exception as exc:
            raise UserError(_(
                "Auto-invoice: invoice was created (draft) but could "
                "not be posted: %s\n\n"
                "Find it in the Accounting drafts and post manually, "
                "or fix the issue and re-validate the delivery."
            ) % exc) from exc

        # Email. We tolerate email failure (warning + activity) but
        # don't roll back the invoice — the document is already real.
        for move in moves:
            try:
                move.with_context(
                    discard_logo_check=True,
                )._ufs_send_invoice_email()
            except Exception as exc:
                _logger.warning(
                    "ufs auto-invoice: failed to email invoice %s: %s",
                    move.name, exc,
                )
                self.env['mail.activity'].sudo().create({
                    'res_model': 'account.move',
                    'res_model_id': self.env['ir.model']._get_id('account.move'),
                    'res_id': move.id,
                    'activity_type_id': self.env.ref(
                        'mail.mail_activity_data_todo'
                    ).id,
                    'summary': _('Auto-invoice: email send failed'),
                    'note': _(
                        "The invoice was created and posted, but the "
                        "automatic email failed: %s. Send manually "
                        "from the invoice."
                    ) % exc,
                    'user_id': order.user_id.id or self.env.user.id,
                })

        self.ufs_invoiced_on_validate = True
        _logger.info(
            "ufs auto-invoice: SO %s delivery %s → invoice(s) %s posted",
            order.name, self.name, ', '.join(moves.mapped('name')),
        )
