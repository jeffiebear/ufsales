# -*- coding: utf-8 -*-
"""
Reusable margin-percentage presets.

A tiny lookup model so admins can add, rename, or retire margin tiers
without a code change. Surfaced as a Many2one dropdown on both sale
order lines and purchase order lines (see the sibling models).

Seeded defaults: 15, 18, 20, 25, 30, 35, 40 %. Edit under
Sales → Configuration → Margin Presets (or the same menu under
Purchase) — both link to the same records.

The formula applied when a preset is chosen:

    price = cost / (1 - margin_pct / 100)

This is **gross margin**, not markup. A 30 % preset against a $10
cost yields $14.29 (margin = 4.29 / 14.29 = 30 %), not $13.00.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UfsMarginPreset(models.Model):
    _name = "ufs.margin.preset"
    _description = "UFS Margin Preset"
    _order = "margin_pct, id"

    name = fields.Char(
        string="Name",
        compute="_compute_name", store=True, readonly=False,
        help="Display label. Auto-fills to '<pct> %' when blank.",
    )
    margin_pct = fields.Float(
        string="Margin %",
        required=True,
        help="Gross margin as a percentage. Example: 30.0 means the "
             "preset will price at cost ÷ 0.70.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("uniq_margin_pct", "unique(margin_pct)",
         "Each margin percentage can exist only once."),
    ]

    @api.depends("margin_pct")
    def _compute_name(self):
        for preset in self:
            if not preset.name:
                # Strip trailing zeroes ("30.0 %" → "30 %") for tidy
                # dropdown labels. Falls back to "0 %" if margin is 0.
                pct = preset.margin_pct or 0.0
                label = ("%g" % pct) + " %"
                preset.name = label

    @api.constrains("margin_pct")
    def _check_margin_below_100(self):
        for preset in self:
            if preset.margin_pct >= 100.0:
                raise ValidationError(
                    "Margin must be below 100 %. A 100 % or higher "
                    "margin would require infinite or negative price."
                )

    def apply_to_cost(self, cost):
        """Return the sell price for a given cost under this margin.

        Helper used by the sale/purchase line onchange handlers. Guards
        against zero cost and the (theoretical) 100 % margin case.
        """
        self.ensure_one()
        if not cost or cost <= 0:
            return 0.0
        denom = 1.0 - (self.margin_pct / 100.0)
        if denom <= 0:
            return 0.0
        return round(cost / denom, 2)
