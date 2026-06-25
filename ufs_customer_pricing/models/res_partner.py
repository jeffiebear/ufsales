# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # STEP1's DefaultPriceOpt — the customer's fall-back pricing scheme.
    # We expose the common values as a selection plus a free-text "raw"
    # field for the cases that don't fit (e.g. 'p35', 'm12').
    ufs_default_price_opt = fields.Char(
        string='Default Pricing Scheme',
        help="The customer's default price for any product they don't have a "
             "specific rule for. Examples: 'I' (catalog list price), 'P50' "
             "(50%% profit margin), 'M40' (40%% markup). This is materialised "
             "as a global rule on the customer's pricelist, so it actually "
             "drives the price. A bare 'P' or 'M' with no number is treated as "
             "unset (falls back to catalog list price) — give it a number to "
             "apply a margin.",
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
        # Materialise the customer's Default Pricing Scheme (e.g. P50) as a
        # global rule so non-overridden products price at that margin.
        self._ufs_sync_default_pricelist_item()
        return pl

    def _ufs_promote_pricelist(self):
        """Make the customer's per-customer UFS pricelist their ORDER pricelist
        and keep its global default item in sync with their Default Pricing
        Scheme.

        A customer's product overrides (ufs.price.rule) sync onto their own
        "Customer Pricelist — X". For every product they DON'T have a specific
        rule for, we materialise a single GLOBAL item from
        ``ufs_default_price_opt`` (e.g. P50 -> a 50%-margin formula on cost).
        Then we point ``property_product_pricelist`` at that pricelist so the
        sale order actually reads these prices. Net effect:

            * product with a specific rule  -> its override (variant wins)
            * every other product           -> the customer's default margin
            * 'I' / unset default           -> catalog list price

        Idempotent.
        """
        for partner in self:
            ufs = partner.ufs_pricelist_id
            if not ufs:
                continue
            partner._ufs_sync_default_pricelist_item()
            if partner.property_product_pricelist.id != ufs.id:
                partner.sudo().write({'property_product_pricelist': ufs.id})

    def _ufs_default_item_plan(self, pricelist):
        """Decide what to do with the GLOBAL default item on ``pricelist``,
        based on this partner's Default Pricing Scheme. Returns a tuple:

            ('set', vals)    -> create/update the global item with these vals
            ('remove', None) -> there must be NO global item (explicit list price)
            ('skip', None)   -> ambiguous/unknown; leave any existing item alone
        """
        self.ensure_one()
        from .ufs_price_rule import parse_step1_price_opt
        rt, num = parse_step1_price_opt(self.ufs_default_price_opt or '')
        # Mirror the exact shape of the per-product margin/markup items built in
        # ufs_price_rule._to_pricelist_item_vals: set only price_markup (Odoo
        # derives the rest). Setting price_discount here too would fight that
        # and can zero the markup out.
        vals = {
            'pricelist_id': pricelist.id,
            'applied_on': '3_global',
            'min_quantity': 0,
            'company_id': pricelist.company_id.id or self.env.company.id,
            'compute_price': 'formula',
            'base': 'standard_price',
            'price_round': 0.01,
        }
        # Profit margin: price = cost / (1 - m/100). With base='standard_price'
        # Odoo applies price = cost * (1 + price_markup/100), so the markup that
        # yields margin m is 100*m/(100-m).
        if rt == 'margin' and 0.0 < num < 100.0:
            vals['price_markup'] = 100.0 * num / (100.0 - num)
            return ('set', vals)
        if rt == 'markup' and num > 0.0:
            vals['price_markup'] = float(num)
            return ('set', vals)
        if rt == 'list':
            # 'I' -> the customer genuinely defaults to catalog list price.
            return ('remove', None)
        # Bare 'P'/'M' (no percentage), 'special', empty/'default', or an
        # out-of-range number: we can't safely invent a margin (a bare 'P'
        # would mean 0% margin = selling at cost). Leave any existing item
        # untouched rather than guess.
        return ('skip', None)

    def _ufs_sync_default_pricelist_item(self):
        """Ensure the GLOBAL default item on each partner's per-customer
        pricelist matches their Default Pricing Scheme (see
        ``_ufs_default_item_plan``)."""
        Item = self.env['product.pricelist.item'].sudo()
        for partner in self:
            pl = partner.ufs_pricelist_id
            if not pl:
                continue
            action, vals = partner._ufs_default_item_plan(pl)
            existing = Item.search([
                ('pricelist_id', '=', pl.id),
                ('applied_on', '=', '3_global'),
            ])
            if action == 'set':
                if existing:
                    existing[0].write(vals)
                    if len(existing) > 1:
                        existing[1:].unlink()
                else:
                    Item.create(vals)
            elif action == 'remove':
                if existing:
                    existing.unlink()
            # 'skip' -> leave existing items untouched.

    def _ufs_reprice_open_orders(self):
        """Realign and reprice this partner's open (draft/sent) sale orders so
        newly-synced rules and default margins show up immediately. Confirmed
        orders are never touched. Best-effort: a reprice failure on one order is
        logged, not raised, so saving a price rule never blocks."""
        Order = self.env['sale.order'].sudo()
        orders = Order.search([
            ('partner_id', 'in', self.ids),
            ('state', 'in', ('draft', 'sent')),
        ])
        for order in orders:
            target = order.partner_id.property_product_pricelist
            try:
                if target and order.pricelist_id.id != target.id:
                    order.pricelist_id = target.id
                if hasattr(order, 'action_update_prices'):
                    order.action_update_prices()
                elif hasattr(order, '_recompute_prices'):
                    order._recompute_prices()
            except Exception as exc:  # noqa: BLE001 - never block a rule save
                _logger.warning(
                    "ufs pricing: could not reprice %s: %s", order.name, exc)

    def write(self, vals):
        res = super().write(vals)
        # When the customer default changes: re-sync any 'default'-type rules,
        # re-materialise the global default item from the new scheme, and
        # reprice open orders so the change is visible right away.
        if 'ufs_default_price_opt' in vals:
            default_rules = self.mapped('ufs_price_rule_ids').filtered(
                lambda r: r.rule_type == 'default'
            )
            if default_rules:
                default_rules._sync_pricelist_item()
            self._ufs_sync_default_pricelist_item()
            self._ufs_reprice_open_orders()
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
