# -*- coding: utf-8 -*-
"""
Sale order — "Create Customer Price Rules" button.

Workflow this supports: an admin builds a manual quote, hand-tunes the
unit prices using the margin guide column, and then wants to lock those
prices in as the customer's go-forward special prices. Clicking the
button on the order header snapshots each line's unit price into a
``ufs.price.rule`` (rule_type=special) for the order's customer.

Conflict policy
---------------
If a rule already exists for (customer, product) — *active or
inactive*, any rule_type — we leave it alone. The button is a
convenience for *new* relationships, not a way to overwrite carefully
hand-tuned rules. Admins who want to override an existing rule should
edit it directly via Sales → Customer Price Rules.

Pricelist hookup
----------------
Creating the first rule on a customer provisions their UFS pricelist
(see ``ufs_customer_pricing/models/res_partner.py``) and writes it to
``partner.property_product_pricelist`` — that's the standard Odoo hook
that makes the pricelist auto-load on the customer's *next* quote. We
also refresh the *current* order's pricelist_id, so any new lines
added to this same quote start picking up the rules immediately.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_ufs_create_price_rules(self):
        """Create Special Price rules from this order's line prices."""
        self.ensure_one()
        Rule = self.env['ufs.price.rule']
        partner = self.partner_id
        if not partner:
            raise UserError(_("Set a customer on the order first."))

        # Collect product IDs that already have *any* rule for this
        # customer + company. We use sudo() so internal sales users
        # without rule-edit rights can still create new ones; the rule
        # ACL on creation is checked by the Rule.create() call below.
        existing_product_ids = set(
            Rule.sudo().with_context(active_test=False).search([
                ('partner_id', '=', partner.id),
                ('company_id', '=', self.company_id.id),
            ]).mapped('product_id.id')
        )

        to_create = []
        seen = set()                # de-dupe within this single order
        skipped_existing = 0
        skipped_no_product = 0
        skipped_no_price = 0

        for line in self.order_line:
            # Section / note lines have no product.
            if not line.product_id or line.display_type:
                skipped_no_product += 1
                continue
            pid = line.product_id.id
            if pid in existing_product_ids:
                skipped_existing += 1
                continue
            if pid in seen:
                # Same product on multiple lines — keep the first one.
                continue
            # A $0 special price is almost always a mistake; skip and
                # let the admin add it manually if they really meant it.
            if not line.price_unit:
                skipped_no_price += 1
                continue
            seen.add(pid)
            to_create.append({
                'partner_id': partner.id,
                'product_id': pid,
                'company_id': self.company_id.id,
                'rule_type': 'special',
                'special_price': line.price_unit,
            })

        created = Rule.create(to_create) if to_create else Rule

        # If creating these rules just provisioned the customer's
        # pricelist (or changed it), align the current order so further
        # lines on this quote pick up the rules natively.
        if created:
            new_pl = partner.property_product_pricelist
            if new_pl and self.pricelist_id != new_pl:
                self.pricelist_id = new_pl

        # Build a single-line human-readable summary for the toast.
        parts = []
        if created:
            parts.append(_("Created %s rule(s)") % len(created))
        if skipped_existing:
            parts.append(_("skipped %s already-ruled") % skipped_existing)
        if skipped_no_price:
            parts.append(_("skipped %s zero-price") % skipped_no_price)
        if skipped_no_product:
            parts.append(_("skipped %s non-product") % skipped_no_product)
        message = ", ".join(parts) if parts else _("No order lines to process.")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Customer Price Rules"),
                'message': message,
                'type': 'success' if created else 'warning',
                'sticky': False,
            },
        }
