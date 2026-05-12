# -*- coding: utf-8 -*-
"""
Settings for the wholesale signup flow.

The "who gets notified when a new wholesale application comes in" list
lives here. Stored as a comma-separated user id list in
ir.config_parameter so it survives module reloads and is easy to script.

Key:
    ufs_wholesale.admin_alert_user_ids   (comma-sep user ids)
"""
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ufs_wholesale_admin_alert_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='ufs_wholesale_admin_alert_rel',
        column1='settings_id', column2='user_id',
        string='Wholesale Application Notifications',
        help="Users who receive an email each time a new wholesale "
             "application is submitted. Configure at least one user "
             "or the alert won't go out.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ufs_wholesale.admin_alert_user_ids', '')
        try:
            ids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            ids = []
        res['ufs_wholesale_admin_alert_user_ids'] = [(6, 0, ids)]
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ids = ','.join(str(uid) for uid in self.ufs_wholesale_admin_alert_user_ids.ids)
        ICP.set_param('ufs_wholesale.admin_alert_user_ids', ids)

    @api.model
    def _ufs_wholesale_admin_partner_ids(self):
        """Return res.partner ids for the configured admin alert recipients."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ufs_wholesale.admin_alert_user_ids', '')
        try:
            uids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            uids = []
        if not uids:
            return []
        users = self.env['res.users'].sudo().browse(uids).exists()
        return users.partner_id.ids
