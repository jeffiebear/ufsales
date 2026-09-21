# -*- coding: utf-8 -*-
"""
Auto-exempt newly created Sales taxes on the wholesale fiscal position.

When a new ``account.tax`` with ``type_tax_use='sale'`` is created, we
automatically add a tax-mapping row on the configured wholesale fiscal
position that REPLACES the new tax with the configured 0% resale tax
(``tax_dest_ids`` = the resale tax), NOT an empty mapping.

Why a 0% tax and not "no tax" (empty ``tax_dest_ids``):
    Dropping the tax entirely leaves the exempt sale with no tax line, so
    its taxable base never lands on any tax report. Replacing it with a 0%
    "Resale" tax charges nothing but keeps the base on the books, which is
    what the Florida DR-15 return needs (exempt sales are reported, not
    invisible). If no resale tax is configured we now SKIP the mapping
    rather than fall back to the old drop-the-tax behavior.

Why this lives here, not as a Settings → Automation rule:
    - Reliability. The override always fires, even from the shell,
      data imports, or other modules that create taxes programmatically.
    - It's versioned with the rest of the wholesale module so it can't
      drift or be accidentally disabled in the UI.

If the operator wants to opt a specific tax OUT of the auto-mapping,
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
        """For each sales tax in self, ensure a mapping exists on the
        configured wholesale fiscal position that replaces it with the 0%
        resale tax. Idempotent."""
        Settings = self.env['res.config.settings'].sudo()
        fp = Settings._ufs_wholesale_fiscal_position()
        if not fp:
            return
        resale = Settings._ufs_wholesale_resale_tax()

        # Never map the resale tax to itself.
        sales_taxes = self.filtered(
            lambda t: t.type_tax_use == 'sale' and t != resale
        )
        if not sales_taxes:
            return

        if not resale:
            # No 0% resale tax configured. Skip rather than fall back to the
            # old empty ("drop the tax") mapping, which would leave the
            # exempt base off every tax report. Surface it so it gets fixed.
            _logger.warning(
                "ufs_wholesale: no 0%% resale tax configured; skipped the "
                "wholesale fiscal-position mapping for %s. Set the Resale "
                "tax under Settings > UFS Wholesale > Tax Treatment.",
                sales_taxes.mapped('name'),
            )
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
                # Replace the tax with the 0% resale tax (NOT empty). Charges
                # nothing but keeps the taxable base on the books for DR-15.
                'tax_dest_ids': [(6, 0, resale.ids)],
            })
        if to_create:
            FPTax.create(to_create)
            _logger.info(
                "ufs_wholesale: mapped %s sales tax(es) to the resale 0%% "
                "tax on fiscal position %s", len(to_create), fp.display_name,
            )
