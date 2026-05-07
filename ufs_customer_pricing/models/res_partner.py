# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # STEP1's DefaultPriceOpt — the customer's fall-back pricing scheme.
    # We expose the common values as a selection plus a free-text "raw"
    # field for the cases that don't fit (e.g. 'p35', 'm12').
    ufs_default_price_opt = fields.Char(
        string='Default Pricing Scheme',
        help="STEP1 DefaultPriceOpt. Examples: 'i' (list price), 'P30' "
             "(30%% profit margin), 'M40' (40%% markup). Used to resolve "
             "rules whose Rule Type is 'Use Customer Default'.",
        default='i',
    )
    ufs_step1_cust_acct = fields.Char(
        string='STEP1 CustAcct', index=True,
        help="STEP1 customer account code, used as the import key.",
    )

    ufs_price_rule_ids = fields.One2many(
        'ufs.price.rule', 'partner_id', string='Customer Price Rules',
    )
    ufs_price_rule_count = fields.Integer(
        compute='_compute_ufs_price_rule_count',
    )

    ufs_pricelist_id = fields.Many2one(
        'product.pricelist', string='UFS Customer Pricelist',
        readonly=True, copy=False,
        help="Auto-generated pricelist that mirrors this customer's "
             "UFS price rules. Do not edit directly — manage via the "
             "Customer Price Rules tab.",
    )

    @api.depends('ufs_price_rule_ids')
    def _compute_ufs_price_rule_count(self):
        groups = self.env['ufs.price.rule']._read_group(
            [('partner_id', 'in', self.ids)],
            groupby=['partner_id'], aggregates=['__count'],
        )
        counts = {p.id: c for p, c in groups}
        for p in self:
            p.ufs_price_rule_count = counts.get(p.id, 0)

    # ----- Pricelist provisioning ----------------------------------------
    def _ufs_get_or_create_pricelist(self):
        """Return this partner's UFS pricelist, creating it on demand and
        linking it as the partner's default sales pricelist."""
        self.ensure_one()
        if self.ufs_pricelist_id:
            return self.ufs_pricelist_id
        Pricelist = self.env['product.pricelist'].sudo()
        pl = Pricelist.create({
            'name': _('Customer Pricelist — %s') % (self.display_name or self.name or self.id),
            'currency_id': self.env.company.currency_id.id,
            'company_id': self.env.company.id,
        })
        self.sudo().write({
            'ufs_pricelist_id': pl.id,
            'property_product_pricelist': pl.id,
        })
        # Seed the new pricelist with mirrors of any existing UFS Quantity
        # Bracket items so brackets keep winning at qty thresholds for
        # this customer too.
        Item = self.env['product.pricelist.item'].sudo()
        bracket_pl = Item._ufs_bracket_pricelist()
        if bracket_pl:
            for src in Item.search([
                ('pricelist_id', '=', bracket_pl.id),
                ('ufs_bracket_source_id', '=', False),
            ]):
                src._ufs_mirror_to(pl)
        return pl

    def write(self, vals):
        res = super().write(vals)
        # When the customer default changes, every rule of type 'default'
        # must re-sync because its effective pricelist item depends on it.
        if 'ufs_default_price_opt' in vals:
            default_rules = self.mapped('ufs_price_rule_ids').filtered(
                lambda r: r.rule_type == 'default'
            )
            if default_rules:
                default_rules._sync_pricelist_item()
        return res

    # ----- Action: open this customer's rules ----------------------------
    def action_open_ufs_price_rules(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Price Rules — %s') % self.display_name,
            'res_model': 'ufs.price.rule',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
