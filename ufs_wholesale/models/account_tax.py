# -*- coding: utf-8 -*-
"""
Auto-exempt newly created Sales taxes on the wholesale fiscal position.

When a new ``account.tax`` with ``type_tax_use='sale'`` is created, we
automatically make the configured wholesale fiscal position REPLACE it
with the configured 0% resale tax, NOT drop it. In Odoo 19 that mapping
lives on ``account.tax`` itself (the resale tax's ``original_tax_ids`` /
``fiscal_position_ids``), because the old ``account.fiscal.position.tax``
model no longer exists.

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
they can remove it from the resale tax's "Replaces" list (its
``original_tax_ids``) after the fact. We only add mappings that don't
already exist, so a manual removal stays removed.
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

        # Domestic sales taxes only (the resale relation's src must be
        # is_domestic), and never the resale tax itself.
        sales_taxes = self.filtered(
            lambda t: t.type_tax_use == 'sale' and t != resale and t.is_domestic
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

        # Odoo 19 stores fiscal-position tax mapping ON account.tax via the
        # self-referential account_tax_alternatives relation (there is no
        # account.fiscal.position.tax model anymore):
        #   resale.original_tax_ids  ("Replaces")  = domestic taxes it replaces
        #   resale.fiscal_position_ids             = positions it applies on
        # A src tax already carrying `resale` in its replacing_tax_ids is
        # already mapped; skip it so this stays idempotent.
        to_map = sales_taxes.filtered(lambda t: resale not in t.replacing_tax_ids)
        if not to_map:
            return
        try:
            resale.sudo().write({
                'original_tax_ids': [(4, t.id) for t in to_map],
                'fiscal_position_ids': [(4, fp.id)],
            })
        except Exception:
            # A courtesy auto-mapping must never break tax creation.
            _logger.exception(
                "ufs_wholesale: failed to map sales tax(es) %s to the resale "
                "0%% tax on fiscal position %s", to_map.mapped('name'), fp.id,
            )
            return
        _logger.info(
            "ufs_wholesale: mapped %s sales tax(es) to the resale 0%% tax on "
            "fiscal position %s", len(to_map), fp.display_name,
        )
