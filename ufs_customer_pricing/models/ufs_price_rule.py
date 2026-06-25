# -*- coding: utf-8 -*-
import re
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# STEP1 price-option parser
# ---------------------------------------------------------------------------
# STEP1 encodes the pricing scheme in two places:
#   * PriceOpt        e.g. 'S', 'P30', 'p25', 'M40', 'B5', 'i', '' (also numeric junk)
#   * CPPriceOpt      single letter type code: 'S', 'P', 'M', 'B', ''
# We normalise both to a tuple (rule_type, numeric_value).
#
# Lowercase variants are treated identically to uppercase, per client direction.
# Empty / 'i' / unrecognised values resolve to 'default' (let the customer
# default decide).

_OPT_RE = re.compile(r'^([SPMBspmb])\s*([0-9]+(?:\.[0-9]+)?)?$')


def parse_step1_price_opt(price_opt, cp_price_opt=None):
    """Return (rule_type, value) or ('default', None) / ('list', None).

    rule_type is one of: 'special', 'margin', 'markup', 'bracket',
    'list', 'default'.
    """
    s = (price_opt or '').strip()
    if not s:
        return ('default', None)
    if s.lower() == 'i':
        return ('list', None)

    m = _OPT_RE.match(s)
    if not m:
        # Numeric or junk values — treat as needing manual review;
        # caller should fall through to default.
        return ('default', None)

    letter = m.group(1).upper()
    num = float(m.group(2)) if m.group(2) is not None else 0.0
    if letter == 'S':
        return ('special', None)        # value carried in CPSpecialPrice
    if letter == 'P':
        return ('margin', num)
    if letter == 'M':
        return ('markup', num)
    if letter == 'B':
        return ('bracket', num)
    return ('default', None)


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------
class UfsPriceRule(models.Model):
    _name = 'ufs.price.rule'
    _description = 'UFS Customer Price Rule'
    _rec_name = 'display_name'
    _order = 'partner_id, product_id'

    # ----- Identity --------------------------------------------------------
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True,
        ondelete='cascade',
        domain=[('customer_rank', '>', 0)],
    )
    product_id = fields.Many2one(
        'product.product', string='Product', required=True, index=True,
        ondelete='cascade',
    )
    product_tmpl_id = fields.Many2one(
        'product.template', related='product_id.product_tmpl_id',
        store=True, readonly=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True,
    )
    display_name = fields.Char(compute='_compute_display_name_field', store=True)

    # ----- Rule type & values ---------------------------------------------
    rule_type = fields.Selection([
        ('special', 'Special Price (fixed)'),
        ('margin',  'Profit Margin %'),
        ('markup',  'Cost Markup %'),
        ('bracket', 'Quantity Bracket'),
        ('list',    'List Price'),
        ('default', 'Use Customer Default'),
    ], string='Rule Type', required=True, default='special')

    special_price = fields.Monetary(
        string='Special Price', currency_field='currency_id',
        help='Fixed selling price. Used when Rule Type = Special Price.',
    )
    margin_pct = fields.Float(
        string='Profit Margin %', digits=(5, 2),
        help='Target profit margin. Selling price = cost / (1 - margin/100). '
             'Recomputes live as cost changes.',
    )
    markup_pct = fields.Float(
        string='Markup %', digits=(5, 2),
        help='Markup over cost. Selling price = cost * (1 + markup/100).',
    )
    bracket_no = fields.Integer(
        string='Bracket #',
        help='STEP1 quantity-bracket tier. Tier sync deferred to v1.1.',
    )

    # Effective price preview (not stored — Odoo's pricelist engine is the
    # source of truth at runtime; this is a convenience for the form view).
    computed_price = fields.Monetary(
        string='Current Price', currency_field='currency_id',
        compute='_compute_computed_price',
    )

    # ----- STEP1 metadata -------------------------------------------------
    step1_price_opt = fields.Char(string='STEP1 PriceOpt (raw)', readonly=True)
    step1_cp_price_opt = fields.Char(string='STEP1 CPPriceOpt (raw)', readonly=True)
    step1_imported = fields.Boolean(string='Imported from STEP1', readonly=True)
    list_price_at_import = fields.Monetary(
        string='List Price (at import)', currency_field='currency_id', readonly=True,
    )
    current_price_at_import = fields.Monetary(
        string='Current Price (at import)', currency_field='currency_id', readonly=True,
    )
    last_price_paid = fields.Monetary(
        string='Last Price Paid', currency_field='currency_id',
    )
    last_qty_ordered = fields.Float(string='Last Qty Ordered')
    first_sale_date = fields.Date(string='First Sale')
    last_sale_date = fields.Date(string='Last Sale')
    next_sale_date = fields.Date(string='Next Expected Sale')

    # ----- Notes & flags --------------------------------------------------
    notes_date = fields.Date(string='Notes Date')
    note1 = fields.Char(string='Note 1')
    note2 = fields.Char(string='Note 2')
    note3 = fields.Char(string='Note 3')
    notes_add_to_order = fields.Boolean(string='Add Notes to Order')
    print_on_order_form = fields.Boolean(string='Print on Order Form', default=True)

    # ----- Customer reference ---------------------------------------------
    customer_part_num = fields.Char(string='Customer Part #')
    sales_class = fields.Char(string='Sales Class')
    tax_flag = fields.Boolean(string='Taxable', default=True)
    commission_flag = fields.Boolean(string='Commissionable', default=True)

    # ----- Validity --------------------------------------------------------
    active = fields.Boolean(default=True)
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')

    # ----- Sync linkage to standard pricelist -----------------------------
    pricelist_item_id = fields.Many2one(
        'product.pricelist.item', string='Linked Pricelist Item',
        ondelete='set null', readonly=True, copy=False,
    )

    _sql_constraints = [
        ('unique_customer_product_company',
         'unique(partner_id, product_id, company_id, date_start)',
         'A rule already exists for this customer / product / start date.'),
    ]

    @api.constrains('rule_type', 'margin_pct')
    def _check_margin_pct(self):
        for r in self:
            if r.rule_type == 'margin' and r.margin_pct >= 100.0:
                raise ValidationError(_(
                    "Profit margin must be less than 100%%."
                ))

    # ----- Defaults -------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        # When the form is opened from a product template's inline list,
        # the context carries default_product_tmpl_id but ufs.price.rule
        # needs a concrete variant (product.product). Translate it here so
        # users can add rules directly from the product form.
        vals = super().default_get(fields_list)
        if 'product_id' in fields_list and not vals.get('product_id'):
            tmpl_id = self.env.context.get('default_product_tmpl_id')
            if tmpl_id:
                tmpl = self.env['product.template'].browse(tmpl_id)
                if len(tmpl.product_variant_ids) == 1:
                    vals['product_id'] = tmpl.product_variant_id.id
        return vals

    # ----- Computeds ------------------------------------------------------
    @api.depends('partner_id', 'product_id')
    def _compute_display_name_field(self):
        for r in self:
            r.display_name = '%s — %s' % (
                r.partner_id.display_name or '',
                r.product_id.display_name or '',
            )

    @api.depends('rule_type', 'special_price', 'margin_pct', 'markup_pct',
                 'product_id', 'product_id.standard_price',
                 'product_id.list_price', 'partner_id')
    def _compute_computed_price(self):
        for r in self:
            r.computed_price = r._evaluate_price()

    def _evaluate_price(self):
        """Return the price this rule currently produces, given today's cost."""
        self.ensure_one()
        rt = self.rule_type
        if rt == 'special':
            return self.special_price or 0.0
        cost = self.product_id.standard_price or 0.0
        if rt == 'margin':
            if self.margin_pct >= 100.0:
                return 0.0
            return cost / (1.0 - self.margin_pct / 100.0)
        if rt == 'markup':
            return cost * (1.0 + self.markup_pct / 100.0)
        if rt == 'list':
            return self.product_id.list_price or 0.0
        if rt == 'default':
            resolved = self._resolve_default()
            if resolved:
                return resolved._evaluate_price_with(self.product_id)
            return self.product_id.list_price or 0.0
        if rt == 'bracket':
            # Multi-tier sync deferred. For preview, return list price.
            return self.product_id.list_price or 0.0
        return 0.0

    def _evaluate_price_with(self, product):
        """Like _evaluate_price but using a passed-in product (for default
        resolution where the rule is a synthesised partner-level default)."""
        self.ensure_one()
        # Delegate by temporarily swapping product_id in a transient copy
        rt = self.rule_type
        cost = product.standard_price or 0.0
        if rt == 'special':
            return self.special_price or 0.0
        if rt == 'margin':
            if self.margin_pct >= 100.0:
                return 0.0
            return cost / (1.0 - self.margin_pct / 100.0)
        if rt == 'markup':
            return cost * (1.0 + self.markup_pct / 100.0)
        return product.list_price or 0.0

    # ----- Default resolution ---------------------------------------------
    def _resolve_default(self):
        """Return a transient (NewId) ufs.price.rule that represents this
        rule resolved via the customer's default scheme. Returns empty
        recordset if the partner default itself is 'list' / unset."""
        self.ensure_one()
        partner = self.partner_id
        opt = (partner.ufs_default_price_opt or '').strip()
        if not opt or opt.lower() == 'list':
            return self.env['ufs.price.rule']
        rt, num = parse_step1_price_opt(opt)
        if rt in ('list', 'default'):
            return self.env['ufs.price.rule']
        # Build an in-memory rule with the resolved type
        new = self.env['ufs.price.rule'].new({
            'partner_id': partner.id,
            'product_id': self.product_id.id,
            'rule_type': rt,
            'margin_pct': num if rt == 'margin' else 0.0,
            'markup_pct': num if rt == 'markup' else 0.0,
        })
        return new

    # ----- Pricelist sync -------------------------------------------------
    def _to_pricelist_item_vals(self):
        """Compute the dict to write on the linked product.pricelist.item.

        Returns None if the rule should NOT produce a pricelist item
        (list-price fall-through, unresolvable defaults, etc.).
        """
        self.ensure_one()
        if not self.active:
            return None
        pricelist = self.partner_id._ufs_get_or_create_pricelist()
        base = {
            'pricelist_id': pricelist.id,
            'applied_on': '0_product_variant',
            'product_id': self.product_id.id,
            'min_quantity': 1,
            'date_start': self.date_start or False,
            'date_end': self.date_end or False,
            'company_id': self.company_id.id,
        }
        rt = self.rule_type

        if rt == 'special':
            base.update({
                'compute_price': 'fixed',
                'fixed_price': self.special_price or 0.0,
            })
            return base

        if rt == 'margin':
            if self.margin_pct >= 100.0:
                raise ValidationError(_(
                    "Profit margin must be less than 100%% (rule for %s / %s)."
                ) % (self.partner_id.display_name, self.product_id.display_name))
            # In Odoo 19, when base='standard_price' the formula uses
            # price_markup: price = cost * (1 + price_markup/100).
            # Margin m means price = cost / (1 - m/100); solving gives
            # price_markup = 100 * m / (100 - m).
            markup = 100.0 * self.margin_pct / (100.0 - self.margin_pct)
            base.update({
                'compute_price': 'formula',
                'base': 'standard_price',
                'price_markup': markup,
                'price_round': 0.01,
            })
            return base

        if rt == 'markup':
            base.update({
                'compute_price': 'formula',
                'base': 'standard_price',
                'price_markup': float(self.markup_pct or 0.0),
                'price_round': 0.01,
            })
            return base

        if rt == 'list':
            # Falls through to product.list_price natively. No item needed.
            return None

        if rt == 'default':
            resolved = self._resolve_default()
            if not resolved:
                return None  # falls through to list price
            # Borrow resolved type/value but keep our own product/partner
            stub = self.new({
                'partner_id': self.partner_id.id,
                'product_id': self.product_id.id,
                'rule_type': resolved.rule_type,
                'margin_pct': resolved.margin_pct,
                'markup_pct': resolved.markup_pct,
                'special_price': resolved.special_price,
                'date_start': self.date_start,
                'date_end': self.date_end,
            })
            return stub._to_pricelist_item_vals()

        if rt == 'bracket':
            # v1: not synced. v1.1 will create one item per tier with min_quantity.
            return None

        return None

    def _sync_pricelist_item(self):
        """Create/update/remove the linked pricelist item to match this rule."""
        Item = self.env['product.pricelist.item']
        for r in self:
            vals = r._to_pricelist_item_vals()
            if vals is None:
                # Rule doesn't need an item — drop any existing link
                if r.pricelist_item_id:
                    r.pricelist_item_id.sudo().unlink()
                    r.pricelist_item_id = False
                continue
            if r.pricelist_item_id:
                r.pricelist_item_id.sudo().write(vals)
            else:
                item = Item.sudo().create(vals)
                r.pricelist_item_id = item.id
        # Make sure each affected customer's order actually uses their own
        # UFS pricelist (carrying their prior margin tier as a fallback), so
        # the overrides we just synced are the ones the sale order sees.
        self.mapped('partner_id')._ufs_promote_pricelist()

    # ----- ORM hooks -------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_pricelist_item()
        return records

    def write(self, vals):
        res = super().write(vals)
        sync_triggers = {
            'rule_type', 'special_price', 'margin_pct', 'markup_pct',
            'bracket_no', 'product_id', 'partner_id', 'date_start',
            'date_end', 'active', 'company_id',
        }
        if sync_triggers & set(vals.keys()):
            self._sync_pricelist_item()
        return res

    def unlink(self):
        items = self.mapped('pricelist_item_id')
        res = super().unlink()
        items.sudo().unlink()
        return res

    # ----- Convenience action --------------------------------------------
    def action_resync_all(self):
        """Manual button: rebuild pricelist items for the selected rules."""
        self._sync_pricelist_item()
        return True
