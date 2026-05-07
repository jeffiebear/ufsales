# -*- coding: utf-8 -*-
"""Bracket-pricing precedence.

Items on the shared "UFS Quantity Brackets" pricelist are mirrored onto
every customer pricelist so Odoo's native min_quantity resolution makes
the bracket price win once the order quantity hits the bracket
threshold — even when the customer also has a special-price rule on
their own pricelist.

Lifecycle:
- Source bracket item created/updated -> mirror is copied/synced onto
  every existing customer pricelist.
- Source bracket item deleted -> mirrors are dropped via the
  `ondelete='cascade'` link on `ufs_bracket_source_id`.
- A new customer pricelist is provisioned -> bracket items are seeded
  by `res.partner._ufs_get_or_create_pricelist`.
"""
from odoo import api, fields, models


BRACKET_PRICELIST_NAME = "UFS Quantity Brackets"


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    ufs_bracket_source_id = fields.Many2one(
        "product.pricelist.item",
        string="UFS Bracket Source",
        ondelete="cascade",
        index=True,
        copy=False,
    )

    @api.model
    def _ufs_bracket_pricelist(self):
        return self.env["product.pricelist"].sudo().search(
            [("name", "=", BRACKET_PRICELIST_NAME)], limit=1,
        )

    @api.model
    def _ufs_customer_pricelists(self):
        partners = self.env["res.partner"].sudo().with_context(
            active_test=False,
        ).search([("ufs_pricelist_id", "!=", False)])
        return partners.mapped("ufs_pricelist_id")

    def _ufs_mirror_to(self, target_pricelist):
        """Idempotently copy this source bracket item to a customer
        pricelist. Returns the mirror item."""
        self.ensure_one()
        if not target_pricelist or target_pricelist == self.pricelist_id:
            return self.browse()
        existing = self.sudo().search([
            ("ufs_bracket_source_id", "=", self.id),
            ("pricelist_id", "=", target_pricelist.id),
        ], limit=1)
        if existing:
            return existing
        return self.sudo().copy({
            "pricelist_id": target_pricelist.id,
            "ufs_bracket_source_id": self.id,
        })

    def _ufs_is_bracket_source(self):
        """True for items that live on the bracket pricelist and aren't
        themselves mirrors."""
        bracket_pl = self._ufs_bracket_pricelist()
        if not bracket_pl:
            return self.browse()
        return self.filtered(
            lambda i: i.pricelist_id == bracket_pl
            and not i.ufs_bracket_source_id,
        )

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        sources = items._ufs_is_bracket_source()
        if sources:
            customer_pls = self._ufs_customer_pricelists()
            for src in sources:
                for pl in customer_pls:
                    src._ufs_mirror_to(pl)
        return items

    def write(self, vals):
        res = super().write(vals)
        # Propagate non-structural field changes to mirrors. Skip writes
        # that only touch the linkage fields themselves.
        propagate = {
            k: v for k, v in vals.items()
            if k not in ("pricelist_id", "ufs_bracket_source_id")
        }
        if not propagate:
            return res
        sources = self._ufs_is_bracket_source()
        if not sources:
            return res
        mirrors = self.sudo().search([
            ("ufs_bracket_source_id", "in", sources.ids),
        ])
        if mirrors:
            mirrors.write(propagate)
        return res
