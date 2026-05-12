# -*- coding: utf-8 -*-
"""
Sale order — confirm-time margin alert + nightly digest collector.

When any line on an order has ``ufs_margin_alert == True`` at confirm
time, we schedule a mail.activity on the order so the salesperson sees
it in their activity inbox. The same flagging also drives the daily
email digest.

We intentionally don't *block* confirmation — this is an awareness
signal, not a gate. Sales staff are expected to review and override
or adjust as needed.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ufs_has_margin_alert = fields.Boolean(
        string='Has Margin Alert',
        compute='_compute_ufs_has_margin_alert',
        store=False,
        help="True when any line on this order is flagged as a "
             "fixed-price line below the margin threshold.",
    )

    @api.depends('order_line.ufs_margin_alert')
    def _compute_ufs_has_margin_alert(self):
        for order in self:
            order.ufs_has_margin_alert = any(
                line.ufs_margin_alert for line in order.order_line
            )

    # ----- Activity on confirm ------------------------------------------
    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            flagged = order.order_line.filtered('ufs_margin_alert')
            if flagged:
                order._ufs_schedule_margin_activity(flagged)
        return res

    def _ufs_schedule_margin_activity(self, flagged_lines):
        """Schedule a TODO activity on the order summarising the flagged
        lines. Idempotent: skips creation if an open margin-alert activity
        already exists on this order."""
        self.ensure_one()
        Activity = self.env['mail.activity'].sudo()
        activity_type = self.env.ref(
            'ufs_alerts.mail_activity_data_margin_alert',
            raise_if_not_found=False,
        ) or self.env.ref('mail.mail_activity_data_todo')

        existing = Activity.search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
        ], limit=1)
        if existing:
            return existing

        lines_summary = "\n".join(
            "  • %s — %.1f%% margin" % (line.product_id.display_name, line.ufs_margin_percent)
            for line in flagged_lines
        )
        note = _(
            "Fixed-price lines on this order are below the margin threshold:\n%s\n\n"
            "Review pricing before fulfilment or confirm acceptance of the lower margin."
        ) % lines_summary

        return Activity.create({
            'res_model': 'sale.order',
            'res_model_id': self.env['ir.model']._get_id('sale.order'),
            'res_id': self.id,
            'activity_type_id': activity_type.id,
            'summary': _('Margin alert: %s line(s) below threshold') % len(flagged_lines),
            'note': note,
            'date_deadline': fields.Date.context_today(self) + timedelta(days=1),
            'user_id': (self.user_id or self.env.user).id,
        })

    # ----- Daily digest -------------------------------------------------
    @api.model
    def _ufs_cron_margin_alert_digest(self):
        """Find orders with any open margin-alert line and email the
        configured digest recipients. Triggered by nightly cron.

        We render the email body in Python rather than via a mail.template
        because the digest references many orders rather than acting on
        a single record."""
        partner_ids = self.env['res.config.settings']._ufs_get_digest_partner_ids()
        if not partner_ids:
            _logger.info("UFS margin digest: no recipients configured, skipping.")
            return

        orders = self.search([
            ('state', 'in', ('draft', 'sent', 'sale')),
        ]).filtered('ufs_has_margin_alert')
        if not orders:
            _logger.info("UFS margin digest: no flagged orders.")
            return

        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', ''
        ).rstrip('/')

        rows = []
        for order in orders.sorted('id'):
            flagged = order.order_line.filtered('ufs_margin_alert')
            lines_html = "".join(
                "<li>%s — <b>%.1f%%</b> margin (price $%.2f, cost $%.2f)</li>" % (
                    line.product_id.display_name,
                    line.ufs_margin_percent,
                    line.price_unit,
                    line.ufs_cost_unit,
                ) for line in flagged
            )
            rows.append(
                "<tr>"
                "<td style='padding:8px;border-bottom:1px solid #eee;vertical-align:top;'>"
                "<a href='%s/odoo/sales/%s'>%s</a><br/>"
                "<span style='color:#666;font-size:12px;'>%s</span>"
                "</td>"
                "<td style='padding:8px;border-bottom:1px solid #eee;'><ul style='margin:0;padding-left:18px;'>%s</ul></td>"
                "</tr>" % (
                    base_url, order.id, order.name,
                    order.partner_id.display_name,
                    lines_html,
                )
            )

        body = (
            "<p>The following open orders have fixed-price lines below the "
            "configured margin threshold. Review when convenient.</p>"
            "<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;'>"
            "<thead><tr style='background:#f6f5ef;text-align:left;'>"
            "<th style='padding:8px;'>Order</th>"
            "<th style='padding:8px;'>Flagged Lines</th>"
            "</tr></thead>"
            "<tbody>%s</tbody></table>"
        ) % "".join(rows)

        mail = self.env['mail.mail'].sudo().create({
            'subject': _("UFS margin alert digest — %s order(s)") % len(orders),
            'body_html': body,
            'recipient_ids': [(6, 0, partner_ids)],
            'auto_delete': True,
        })
        mail.send()
        _logger.info("UFS margin digest: sent for %s orders to %s recipients",
                     len(orders), len(partner_ids))
