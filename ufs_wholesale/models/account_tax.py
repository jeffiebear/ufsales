# -*- coding: utf-8 -*-
"""
Auto-exempt newly created Sales taxes on the wholesale fiscal position.

When a new ``account.tax`` with ``type_tax_use='sale'`` is created, we
automatically add a tax-mapping row on the configured wholesale fiscal
position that maps the new tax to "no tax" (empty ``tax_dest_ids``).

Why this lives here, not as a Settings → Automation rule:
    - Reliability. The override always fires, even from the shell,
      data imports, or other modules that create taxes programmatically.
    - It's versioned with the rest of the wholesale module so it can't
      drift or be accidentally disabled in the UI.

If the operator wants to opt a specific tax OUT of the auto-exemption,
they can remove the generated ``account.fiscal.position.tax`` row from
the fiscal position after the fact. We skip duplicates on re-create, so
removed rows stay removed.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model_create_multi
    def create(self, vals_list):
        taxes = super().create(vals_list)
        taxes._ufs_sync_to_wholesale_fiscal_position()
        return taxes

    def write(self, vals):
        res = super().write(vals)
        # If a tax's type changes TO 'sale', sync it now. Going the
        # other way (sale -> purchase) doesn't auto-clean up the
        # existing fiscal position row; admins can remove it manually
        # if it bothers them.
        if 'type_tax_use' in vals and vals.get('type_tax_use') == 'sale':
            self._ufs_sync_to_wholesale_fiscal_position()
        return res

    def _ufs_sync_to_wholesale_fiscal_position(self):
        """For each sales tax in self, ensure an exemption mapping
        exists on the configured wholesale fiscal position. Idempotent."""
        sales_taxes = self.filtered(lambda t: t.type_tax_use == 'sale')
        if not sales_taxes:
            return
        fp = self.env['res.config.settings'].sudo()._ufs_wholesale_fiscal_position()
        if not fp:
            return

        FPTax = self.env['account.fiscal.position.tax'].sudo()
        # One bulk read of existing mappings to skip duplicates.
        existing_src_ids = set(FPTax.search([
            ('position_id', '=', fp.id),
            ('tax_src_id', 'in', sales_taxes.ids),
        ]).mapped('tax_src_id.id'))

        to_create = []
        for tax in sales_taxes:
            if tax.id in existing_src_ids:
                continue
            to_create.append({
                'position_id': fp.id,
                'tax_src_id': tax.id,
                # Empty tax_dest_ids = "drop this tax entirely for
                # customers on this fiscal position". That's the
                # exemption mapping.
                'tax_dest_ids': [(6, 0, [])],
            })
        if to_create:
            FPTax.create(to_create)
            _logger.info(
                "ufs_wholesale: added %s sales tax exemption(s) to "
                "fiscal position %s", len(to_create), fp.display_name,
            )
