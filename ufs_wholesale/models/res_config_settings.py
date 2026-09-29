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

    # Fiscal position auto-applied when a wholesale application is
    # approved, and the destination of the auto-exemption mapping for
    # newly-created sales taxes. Defaults to account.fiscal.position(3)
    # in UFS (the resale exemption position), but stored as a real
    # config-parameter many2one so admins can repoint without code.
    ufs_wholesale_fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Wholesale Fiscal Position',
        config_parameter='ufs_wholesale.fiscal_position_id',
        help="Auto-applied to a customer's partner record when their "
             "wholesale application is approved. Also receives a "
             "zero-rate tax mapping for every newly created Sales tax, "
             "so resale-exempt customers never get charged a new tax "
             "you add to the catalog later.",
    )

    # The 0%-rate sales tax that REPLACES a normal sales tax on the wholesale
    # fiscal position. Using a real 0% tax (instead of dropping the tax
    # entirely) keeps the exempt sale on the books so its taxable base still
    # reports on the Florida DR-15 return. Stored as a config parameter so it
    # is per-database and repointable without code.
    ufs_wholesale_resale_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Resale (0%) Tax',
        config_parameter='ufs_wholesale.resale_tax_id',
        domain="[('type_tax_use', '=', 'sale')]",
        help="Zero-rate sales tax used to REPLACE the normal sales tax for "
             "customers on the wholesale fiscal position. A 0% tax keeps the "
             "exempt sale's taxable base on the books (for the Florida DR-15 "
             "return) instead of dropping the tax line entirely.",
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
    def _ufs_wholesale_fiscal_position(self):
        """Return the configured wholesale fiscal position, or empty
        recordset. Reads ir.config_parameter directly so callers can
        use this without instantiating a settings record."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('ufs_wholesale.fiscal_position_id', '')
        try:
            fp_id = int(raw)
        except (TypeError, ValueError):
            return self.env['account.fiscal.position']
        if not fp_id:
            return self.env['account.fiscal.position']
        return self.env['account.fiscal.position'].sudo().browse(fp_id).exists()

    @api.model
    def _ufs_wholesale_resale_tax(self):
        """Return the 0% resale tax used to REPLACE sales taxes on the
        wholesale fiscal position, or an empty recordset.

        Resolved so the module is portable across databases (staging vs
        production ids differ) without a hardcoded id:
            1. the ufs_wholesale.resale_tax_id config parameter, if it still
               points at a live tax;
            2. otherwise the first active 0% *sales* tax named "0% Resale"
               (then "...Resale..."), whose id is cached back into the
               parameter so the lookup is stable and an admin can see/repoint
               it under Settings > UFS Wholesale.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        Tax = self.env['account.tax'].sudo()
        raw = ICP.get_param('ufs_wholesale.resale_tax_id', '')
        try:
            tax_id = int(raw)
        except (TypeError, ValueError):
            tax_id = 0
        if tax_id:
            tax = Tax.browse(tax_id).exists()
            if tax:
                return tax
        tax = Tax.search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', 0.0),
            ('name', '=ilike', '0% Resale'),
        ], limit=1)
        if not tax:
            tax = Tax.search([
                ('type_tax_use', '=', 'sale'),
                ('amount', '=', 0.0),
                ('name', 'ilike', 'Resale'),
            ], limit=1)
        if tax:
            ICP.set_param('ufs_wholesale.resale_tax_id', str(tax.id))
        return tax

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
