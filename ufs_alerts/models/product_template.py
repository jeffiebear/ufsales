# -*- coding: utf-8 -*-
"""
Product template — Inventory Alert.

Three computed fields plus one manual override:

    ufs_annual_moving_qty            — stored, refreshed nightly. Sum of
                                        sale.order.line.product_uom_qty
                                        over the last 365 days, restricted
                                        to confirmed orders (state in sale,
                                        done).
    ufs_inventory_alert_override     — manual fixed threshold (optional).
                                        When set, this absolute number
                                        wins over the percentage rule.
    ufs_inventory_alert_threshold    — computed: override if set,
                                        otherwise (annual_moving_qty *
                                        global pct / 100).
    ufs_inventory_alert_active       — computed: True when on-hand qty
                                        <= threshold AND annual moving > 0.
                                        Products with no sales history
                                        are never flagged.

Refresh + alerting is driven by two crons:
    _ufs_cron_recompute_annual_moving  — nightly, recomputes the stored
                                          annual_moving_qty for every
                                          tracked product.
    _ufs_cron_inventory_alert          — nightly, opens activities on
                                          flagged products and emails
                                          the digest.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Tracked types — only physical/consumable products participate.
_TRACKED_TYPES = ('consu', 'product')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ufs_annual_moving_qty = fields.Float(
        string='Annual Moving Qty',
        digits='Product Unit of Measure',
        readonly=True, copy=False,
        help="Rolling 365-day total of confirmed sales quantity. "
             "Refreshed nightly by the UFS Alerts cron. Read-only.",
    )

    ufs_inventory_alert_override = fields.Float(
        string='Fixed Reorder Threshold',
        digits='Product Unit of Measure', copy=False,
        help="Optional fixed alert threshold. When set, the alert fires "
             "as soon as on-hand qty reaches this absolute number, "
             "ignoring the 10%-of-annual-moving rule.",
    )

    ufs_inventory_alert_threshold = fields.Float(
        string='Effective Threshold',
        compute='_compute_ufs_inventory_alert',
        digits='Product Unit of Measure',
        help="The number that actually triggers the alert. Fixed "
             "Reorder Threshold if set; otherwise the configured "
             "percentage of Annual Moving Qty.",
    )

    ufs_inventory_alert_active = fields.Boolean(
        string='Below Reorder Threshold',
        compute='_compute_ufs_inventory_alert',
        search='_search_ufs_inventory_alert_active',
        help="True when on-hand quantity is at or below the effective "
             "threshold. Products with zero annual moving and no "
             "override are never flagged (no false positives on brand-"
             "new SKUs without sales history).",
    )

    @api.depends(
        'ufs_annual_moving_qty',
        'ufs_inventory_alert_override',
        'qty_available',
    )
    def _compute_ufs_inventory_alert(self):
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            pct = float(ICP.get_param('ufs_alerts.inventory_threshold_pct', 10.0))
        except (TypeError, ValueError):
            pct = 10.0

        for tmpl in self:
            override = tmpl.ufs_inventory_alert_override
            moving = tmpl.ufs_annual_moving_qty
            if override and override > 0:
                threshold = override
                has_basis = True
            elif moving > 0:
                threshold = moving * (pct / 100.0)
                has_basis = True
            else:
                threshold = 0.0
                has_basis = False
            tmpl.ufs_inventory_alert_threshold = threshold
            tmpl.ufs_inventory_alert_active = bool(
                has_basis
                and threshold > 0
                and tmpl.qty_available <= threshold
            )

    def _search_ufs_inventory_alert_active(self, operator, value):
        """Search support so the menu filter works."""
        if operator not in ('=', '!='):
            return [('id', '=', False)]
        want_active = bool(value) if operator == '=' else not bool(value)
        # Materialise the compute by scanning candidates.
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            pct = float(ICP.get_param('ufs_alerts.inventory_threshold_pct', 10.0))
        except (TypeError, ValueError):
            pct = 10.0
        candidates = self.search([
            ('type', 'in', _TRACKED_TYPES),
        ])
        matched_ids = []
        for tmpl in candidates:
            override = tmpl.ufs_inventory_alert_override
            moving = tmpl.ufs_annual_moving_qty
            if override and override > 0:
                threshold, has_basis = override, True
            elif moving > 0:
                threshold, has_basis = moving * pct / 100.0, True
            else:
                threshold, has_basis = 0.0, False
            is_active = bool(
                has_basis and threshold > 0 and tmpl.qty_available <= threshold
            )
            if is_active == want_active:
                matched_ids.append(tmpl.id)
        return [('id', 'in', matched_ids)]

    # ----- Crons --------------------------------------------------------
    @api.model
    def _ufs_cron_recompute_annual_moving(self):
        """Recompute ufs_annual_moving_qty for every tracked product
        based on the last 365 days of confirmed sales."""
        cutoff = fields.Datetime.now() - timedelta(days=365)
        groups = self.env['sale.order.line']._read_group(
            domain=[
                ('order_id.state', 'in', ('sale', 'done')),
                ('order_id.date_order', '>=', cutoff),
                ('product_id.type', 'in', _TRACKED_TYPES),
            ],
            groupby=['product_id'],
            aggregates=['product_uom_qty:sum'],
        )
        totals = {p.product_tmpl_id.id: qty for p, qty in groups}

        tracked = self.search([('type', 'in', _TRACKED_TYPES)])
        updated = 0
        for tmpl in tracked:
            new_val = totals.get(tmpl.id, 0.0)
            if abs(tmpl.ufs_annual_moving_qty - new_val) > 1e-6:
                tmpl.ufs_annual_moving_qty = new_val
                updated += 1
        _logger.info(
            "UFS inventory: recomputed annual moving qty for %s products "
            "(of %s tracked)", updated, len(tracked),
        )
        return True

    @api.model
    def _ufs_cron_inventory_alert(self):
        """Open activities on flagged products + send digest email."""
        flagged = self.search([
            ('type', 'in', _TRACKED_TYPES),
            ('ufs_inventory_alert_active', '=', True),
        ])
        if not flagged:
            _logger.info("UFS inventory alert: nothing flagged.")
            return

        # Per-product activity (idempotent).
        Activity = self.env['mail.activity'].sudo()
        activity_type = self.env.ref(
            'ufs_alerts.mail_activity_data_inventory_alert',
            raise_if_not_found=False,
        ) or self.env.ref('mail.mail_activity_data_todo')

        # Activity is assigned to the first configured digest user (the
        # "purchaser") if one is set; otherwise to the cron's own user.
        digest_user_ids = self._ufs_digest_user_ids()
        owner = (
            self.env['res.users'].sudo().browse(digest_user_ids)[:1]
            if digest_user_ids else self.env.user
        )

        for tmpl in flagged:
            existing = Activity.search([
                ('res_model', '=', 'product.template'),
                ('res_id', '=', tmpl.id),
                ('activity_type_id', '=', activity_type.id),
            ], limit=1)
            if existing:
                continue
            Activity.create({
                'res_model': 'product.template',
                'res_model_id': self.env['ir.model']._get_id('product.template'),
                'res_id': tmpl.id,
                'activity_type_id': activity_type.id,
                'summary': _('Reorder: on-hand %.1f ≤ threshold %.1f') % (
                    tmpl.qty_available, tmpl.ufs_inventory_alert_threshold,
                ),
                'note': _(
                    "On-hand quantity is at or below the reorder threshold.\n"
                    "On hand: %.2f  |  Threshold: %.2f  |  Annual moving: %.0f"
                ) % (
                    tmpl.qty_available,
                    tmpl.ufs_inventory_alert_threshold,
                    tmpl.ufs_annual_moving_qty,
                ),
                'date_deadline': fields.Date.context_today(self) + timedelta(days=2),
                'user_id': owner.id,
            })

        # Digest email.
        partner_ids = self.env['res.config.settings']._ufs_get_digest_partner_ids()
        if not partner_ids:
            _logger.info("UFS inventory alert: no digest recipients, skipping email.")
            return

        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', ''
        ).rstrip('/')

        rows = []
        for tmpl in flagged.sorted(lambda t: -t.ufs_annual_moving_qty):
            rows.append(
                "<tr>"
                "<td style='padding:8px;border-bottom:1px solid #eee;'>"
                "<a href='%s/odoo/inventory/products/%s'>%s</a>"
                "</td>"
                "<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;'>%.1f</td>"
                "<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;'>%.1f</td>"
                "<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;color:#666;'>%.0f</td>"
                "</tr>" % (
                    base_url, tmpl.id, tmpl.display_name,
                    tmpl.qty_available,
                    tmpl.ufs_inventory_alert_threshold,
                    tmpl.ufs_annual_moving_qty,
                )
            )

        body = (
            "<p>The following %s product(s) are at or below their reorder "
            "threshold. Threshold defaults to 10%% of the rolling 365-day "
            "sales volume; per-product overrides are honored.</p>"
            "<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;'>"
            "<thead><tr style='background:#f6f5ef;text-align:left;'>"
            "<th style='padding:8px;'>Product</th>"
            "<th style='padding:8px;text-align:right;'>On Hand</th>"
            "<th style='padding:8px;text-align:right;'>Threshold</th>"
            "<th style='padding:8px;text-align:right;color:#666;'>Annual Moving</th>"
            "</tr></thead>"
            "<tbody>%s</tbody></table>"
        ) % (len(flagged), "".join(rows))

        mail = self.env['mail.mail'].sudo().create({
            'subject': _("UFS inventory alert — %s product(s) at or below threshold") % len(flagged),
            'body_html': body,
            'recipient_ids': [(6, 0, partner_ids)],
            'auto_delete': True,
        })
        mail.send()
        _logger.info("UFS inventory alert: digest sent for %s products to %s recipients",
                     len(flagged), len(partner_ids))

    @api.model
    def _ufs_digest_user_ids(self):
        """Helper: return res.users ids configured as digest recipients."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ufs_alerts.digest_recipient_ids', '')
        try:
            return [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            return []
