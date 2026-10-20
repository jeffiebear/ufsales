# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .chatter_policy import HARD_MAX_WIDTH


class ParameterChatterRule(models.Model):
    _name = "parameter.chatter.rule"
    _description = "Chatter Workspace team default"
    _order = "priority, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(
        default=10,
        required=True,
        help="Rules are checked from the lowest number to the highest. The first rule "
        "whose forms and groups match the user wins; equal numbers are resolved by "
        "creation order (oldest first). Rules are never combined.",
    )
    model_ids = fields.Many2many(
        "ir.model",
        "parameter_chatter_rule_ir_model_rel",
        "rule_id",
        "model_id",
        string="Forms",
        domain=[("transient", "=", False)],
        ondelete="cascade",
        help="Leave empty to apply to every form with a chatter.",
    )
    group_ids = fields.Many2many(
        "res.groups",
        "parameter_chatter_rule_res_groups_rel",
        "rule_id",
        "group_id",
        string="User Groups",
        help="Users in any of these groups (including implied groups) match. "
        "Leave empty to apply to all internal users.",
    )
    layout = fields.Selection(
        [
            ("standard", "Standard"),
            ("conversation", "Conversation"),
            ("review", "Review"),
            ("floating", "Floating panel"),
        ],
        help="Leave empty to keep the global default layout.",
    )
    dock_state = fields.Selection(
        [("open", "Open"), ("docked", "Collapsed (Data Entry)")],
        string="Chatter",
        help="Leave empty to keep the global default.",
    )
    width = fields.Integer(
        string="Default Width (px)",
        help="Side chatter width for the Standard layout. 0 keeps the global default. "
        "Clamped to the global minimum and maximum.",
    )
    lock_layout = fields.Boolean(
        string="Lock Layout",
        help="Users matching this rule cannot change the layout or collapse state.",
    )
    lock_width = fields.Boolean(
        string="Lock Width",
        help="Users matching this rule cannot resize the side chatter.",
    )
    summary = fields.Char(compute="_compute_summary")

    @api.constrains("width")
    def _check_width(self):
        for rule in self:
            if rule.width < 0 or rule.width > HARD_MAX_WIDTH:
                raise ValidationError(
                    _("The default width must be 0 (keep default) or a positive width up to "
                      "%(max)s pixels.", max=HARD_MAX_WIDTH)
                )

    @api.depends("model_ids", "group_ids")
    def _compute_summary(self):
        for rule in self:
            forms = ", ".join(rule.model_ids.mapped("name")) or _("All forms")
            groups = ", ".join(rule.group_ids.mapped("display_name")) or _("All users")
            rule.summary = f"{forms} · {groups}"
