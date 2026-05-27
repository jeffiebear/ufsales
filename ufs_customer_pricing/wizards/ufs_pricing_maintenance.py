# -*- coding: utf-8 -*-
"""One-shot pricing maintenance actions.

Two buttons surface the broad-stroke operations admins occasionally
need to apply across the whole catalog:

- Wipe Quantity Brackets — clears every item on the shared bracket
  pricelist (and the mirrors copied onto each customer pricelist).
- Reprice all to 30% margin — sets `list_price = standard_price / 0.70`
  on every active product with a positive cost. This is a true 30 %
  gross margin (margin / price = 0.30), not a 30 % markup. To switch
  back to markup the formula would be `standard_price * 1.30`.
"""
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class UfsPricingMaintenance(models.TransientModel):
    _name = "ufs.pricing.maintenance"
    _description = "UFS Pricing Maintenance"

    log = fields.Text(readonly=True)

    def action_wipe_brackets(self):
        self.ensure_one()
        Item = self.env["product.pricelist.item"].sudo()
        bracket_pl = Item._ufs_bracket_pricelist()
        if not bracket_pl:
            self.log = _("No 'UFS Quantity Brackets' pricelist found.")
            return self._reload()
        sources = Item.search([
            ("pricelist_id", "=", bracket_pl.id),
            ("ufs_bracket_source_id", "=", False),
        ])
        mirrors = Item.search([
            ("ufs_bracket_source_id", "in", sources.ids),
        ])
        n_sources = len(sources)
        n_mirrors = len(mirrors)
        # ondelete=cascade on ufs_bracket_source_id removes the mirrors
        # along with their sources, but unlink them explicitly so the
        # log count is honest.
        mirrors.unlink()
        sources.unlink()
        msg = _("Removed %s bracket source items + %s mirrors.") % (
            n_sources, n_mirrors,
        )
        _logger.info("UFS pricing maintenance: %s", msg)
        self.log = msg
        return self._reload()

    def action_reprice_30(self):
        """Reprice every product to a true 30 % gross margin.

        Formula: list_price = standard_price / 0.70.  A $10 cost becomes
        $14.29, yielding margin = 4.29 / 14.29 = 30 %. (Compare to a
        30 % markup, which would be $13.00 and only ~23 % margin.)
        """
        self.ensure_one()
        Template = self.env["product.template"].sudo()
        templates = Template.with_context(active_test=False).search([
            ("standard_price", ">", 0),
        ])
        updated = unchanged = 0
        for tmpl in templates:
            new_price = round(tmpl.standard_price / 0.70, 2)
            if abs(tmpl.list_price - new_price) > 0.0001:
                tmpl.list_price = new_price
                updated += 1
            else:
                unchanged += 1
        msg = _(
            "Repriced %s products to 30%% margin "
            "(price = cost / 0.70). %s already matched. "
            "Products with no cost were skipped."
        ) % (updated, unchanged)
        _logger.info("UFS pricing maintenance: %s", msg)
        self.log = msg
        return self._reload()

    def _reload(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
