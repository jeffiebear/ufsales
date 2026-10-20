# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo import _, api, fields, models

from .chatter_policy import SETTINGS_SPEC

# res.config.settings field name -> policy setting name
FIELD_MAP = {f"pcw_{name}": name for name in SETTINGS_SPEC}


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pcw_enable_resize = fields.Boolean("Resizable chatter")
    pcw_enable_dock = fields.Boolean("Collapsible chatter")
    pcw_enable_float = fields.Boolean("Floating chatter panel")
    pcw_enable_presets = fields.Boolean("Task layouts")
    pcw_allow_personal = fields.Boolean("Personal layouts")
    pcw_remember_per_model = fields.Boolean("Remember layouts per form type")
    pcw_min_width = fields.Integer("Minimum chatter width")
    pcw_max_width = fields.Integer("Maximum chatter width")
    pcw_default_width = fields.Integer("Default chatter width")
    pcw_default_layout = fields.Selection(
        [
            ("standard", "Standard"),
            ("conversation", "Conversation"),
            ("review", "Review"),
            ("floating", "Floating panel"),
        ],
        string="Default layout",
    )
    pcw_default_dock_state = fields.Selection(
        [("open", "Open"), ("docked", "Collapsed (Data Entry)")],
        string="Chatter starts",
    )
    pcw_rule_count = fields.Integer(compute="_compute_pcw_rule_count")
    pcw_preference_count = fields.Integer(compute="_compute_pcw_preference_count")

    def _compute_pcw_rule_count(self):
        count = self.env["parameter.chatter.rule"].sudo().search_count([])
        for record in self:
            record.pcw_rule_count = count

    def _compute_pcw_preference_count(self):
        count = self.env["parameter.chatter.preference"].sudo().search_count([("has_values", "=", True)])
        for record in self:
            record.pcw_preference_count = count

    @api.model
    def get_values(self):
        res = super().get_values()
        values = self.env["parameter.chatter.policy"]._get_settings()
        res.update({field: values[name] for field, name in FIELD_MAP.items()})
        return res

    def set_values(self):
        super().set_values()
        if not self.env.user.has_group("base.group_system"):
            return
        values = {name: self[field] for field, name in FIELD_MAP.items()}
        values["min_width"] = values["min_width"] or 0
        values["max_width"] = values["max_width"] or 0
        values["default_width"] = values["default_width"] or 0
        self.env["parameter.chatter.policy"]._set_settings(values)

    def action_pcw_reset_all_preferences(self):
        """Remove every user's personal layouts (confirmed in the view)."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            return False
        self.env["parameter.chatter.preference"].sudo().search([]).unlink()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("All personal chatter layouts were removed. Team defaults now apply."),
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
