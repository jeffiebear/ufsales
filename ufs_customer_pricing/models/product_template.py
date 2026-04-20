# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ufs_step1_item_code = fields.Char(
        string='STEP1 Item Code', index=True,
        help="STEP1 ItemCode, used as the import key.",
    )

    ufs_customer_rule_ids = fields.One2many(
        'ufs.price.rule', 'product_tmpl_id',
        string='Customer Pricing Rules',
    )
    ufs_customer_rule_count = fields.Integer(
        compute='_compute_ufs_customer_rule_count',
    )

    @api.depends('ufs_customer_rule_ids')
    def _compute_ufs_customer_rule_count(self):
        groups = self.env['ufs.price.rule']._read_group(
            [('product_tmpl_id', 'in', self.ids)],
            groupby=['product_tmpl_id'], aggregates=['__count'],
        )
        counts = {t.id: c for t, c in groups}
        for t in self:
            t.ufs_customer_rule_count = counts.get(t.id, 0)

    def action_open_ufs_customer_rules(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Pricing — %s') % self.display_name,
            'res_model': 'ufs.price.rule',
            'view_mode': 'list,form',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {'default_product_tmpl_id': self.id},
        }
