# -*- coding: utf-8 -*-
"""
Sale order line — Customer Price column + Edit Rule action.

Surfaces the customer's standing price rule (``ufs.price.rule``) for
the line's product on the sale order. The salesperson sees, at a
glance:

  * The actual unit price on this order line (price_unit, native).
  * The price the customer is "supposed to" pay per their rule
    (ufs_customer_price, computed here).
  * The rule type label (Special / Margin% / Markup% / Bracket / etc.)
    so they know *why* the customer gets the price they get.
  * A pencil-icon button that opens the rule for editing in a modal.

When no rule exists for that customer + product, the column is blank —
intentional: blank means "no special handling, falls back to catalog
price." That's a meaningful signal on its own.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    ufs_customer_rule_id = fields.Many2one(
        'ufs.price.rule',
        string='Customer Rule',
        compute='_compute_ufs_customer_rule',
        store=False,
        groups='sales_team.group_sale_salesman',
        help="The active customer/product price rule for this line's "
             "partner and product, if one exists. Compute-only — to "
             "edit, click the Edit Rule button.",
    )

    ufs_customer_price = fields.Monetary(
        string='Customer Price',
        compute='_compute_ufs_customer_rule',
        store=False,
        currency_field='currency_id',
        groups='sales_team.group_sale_salesman',
        help="The effective price this customer should pay per their "
             "price rule. Blank means no rule on file — line falls "
             "back to catalog list_price. Click Edit Rule to change.",
    )

    ufs_customer_rule_label = fields.Char(
        string='Rule',
        compute='_compute_ufs_customer_rule',
        store=False,
        groups='sales_team.group_sale_salesman',
        help="Short label describing the rule type and its key value "
             "(e.g. 'Margin 30%', 'Markup 25%', 'Bracket #2'). Used "
             "in the column header alongside the numeric price.",
    )

    @api.depends('product_id', 'order_id.partner_id')
    def _compute_ufs_customer_rule(self):
        Rule = self.env['ufs.price.rule'].sudo()
        for line in self:
            partner = line.order_id.partner_id
            product = line.product_id
            if not partner or not product:
                line.ufs_customer_rule_id = False
                line.ufs_customer_price = 0.0
                line.ufs_customer_rule_label = False
                continue
            # Search the customer's rules. Variant first, then template
            # (in case the rule was set on the template only).
            rule = Rule.search([
                ('partner_id', '=', partner.id),
                ('product_id', '=', product.id),
                ('active', '=', True),
            ], limit=1, order='id desc')
            if not rule:
                rule = Rule.search([
                    ('partner_id', '=', partner.id),
                    ('product_tmpl_id', '=', product.product_tmpl_id.id),
                    ('active', '=', True),
                ], limit=1, order='id desc')
            line.ufs_customer_rule_id = rule.id if rule else False
            if rule:
                line.ufs_customer_price = rule._evaluate_price()
                line.ufs_customer_rule_label = line._ufs_rule_label(rule)
            else:
                line.ufs_customer_price = 0.0
                line.ufs_customer_rule_label = False

    @staticmethod
    def _ufs_rule_label(rule):
        rt = rule.rule_type
        if rt == 'special':
            return _("Special")
        if rt == 'margin':
            return _("Margin %.0f%%") % (rule.margin_pct or 0.0)
        if rt == 'markup':
            return _("Markup %.0f%%") % (rule.markup_pct or 0.0)
        if rt == 'bracket':
            return _("Bracket #%s") % (rule.bracket_no or 1)
        if rt == 'list':
            return _("List")
        if rt == 'default':
            return _("Default")
        return rt or ''

    def action_ufs_edit_customer_rule(self):
        """Open the customer's price rule in a modal.

        - If a rule already exists for this partner+product, open it.
        - If not, open a fresh ufs.price.rule form pre-filled with the
          partner, product, and (as a sane starting value) the current
          line's unit price as a Special Price.

        Saving the modal cascades into product.pricelist.item (via the
        rule's standard write hook), which means the customer's
        pricelist updates, which means subsequent SO-line price reads
        see the new price natively. No magic required here.
        """
        self.ensure_one()
        if not self.order_id.partner_id or not self.product_id:
            return False

        Rule = self.env['ufs.price.rule'].sudo()
        rule = self.ufs_customer_rule_id
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'ufs.price.rule',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.order_id.partner_id.id,
                'default_product_id': self.product_id.id,
                'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
                # Pre-fill a Special Price equal to the current line
                # unit price. The user can change rule_type once the
                # modal opens — fields swap automatically.
                'default_rule_type': 'special',
                'default_special_price': self.price_unit,
            },
        }
        if rule:
            action['res_id'] = rule.id
            # Drop the defaults — we're editing an existing record.
            action['context'] = {}
        return action
