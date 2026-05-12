# -*- coding: utf-8 -*-
"""
Global settings for UFS alerts.

Both alert types are tuned from one place: General Settings → UFS Alerts.
Values land in ir.config_parameter so they're company-agnostic and easy
to script from the shell if needed.

Keys:
    ufs_alerts.fixed_price_margin_threshold  (float, %)
    ufs_alerts.inventory_threshold_pct       (float, %)  default 10%
    ufs_alerts.digest_recipient_ids          (comma-sep user ids)
"""
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ----- Margin alert ---------------------------------------------------
    ufs_fixed_price_margin_threshold = fields.Float(
        string='Fixed-Price Margin Threshold (%)',
        config_parameter='ufs_alerts.fixed_price_margin_threshold',
        default=18.0,
        help="When a sale order line uses a customer Special Price rule "
             "and the line's margin % falls below this number, the line "
             "is flagged and the order gets a scheduled activity. "
             "Default 18%.",
    )

    # ----- Inventory alert ------------------------------------------------
    ufs_inventory_threshold_pct = fields.Float(
        string='Inventory Alert Threshold (% of annual moving)',
        config_parameter='ufs_alerts.inventory_threshold_pct',
        default=10.0,
        help="A product is flagged when on-hand quantity is at or below "
             "this percentage of its rolling 365-day sales volume. "
             "Default 10%. Overridable per-product on the product form.",
    )

    # ----- Digest --------------------------------------------------------
    ufs_alerts_digest_recipient_ids = fields.Many2many(
        comodel_name='res.users',
        relation='ufs_alerts_digest_recipient_rel',
        column1='settings_id', column2='user_id',
        string='Digest Recipients',
        help="Users who receive the daily UFS Alerts digest email. "
             "Stored as a comma-separated user-id list in "
             "ir.config_parameter (ufs_alerts.digest_recipient_ids).",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ufs_alerts.digest_recipient_ids', '')
        try:
            ids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            ids = []
        res['ufs_alerts_digest_recipient_ids'] = [(6, 0, ids)]
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ids = ','.join(str(uid) for uid in self.ufs_alerts_digest_recipient_ids.ids)
        ICP.set_param('ufs_alerts.digest_recipient_ids', ids)

    # ----- Helpers callable from anywhere --------------------------------
    @api.model
    def _ufs_get_digest_partner_ids(self):
        """Return res.partner ids for the configured digest recipients."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ufs_alerts.digest_recipient_ids', '')
        try:
            uids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            uids = []
        if not uids:
            return []
        users = self.env['res.users'].sudo().browse(uids).exists()
        return users.partner_id.ids
