# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from markupsafe import Markup, escape

from odoo import _, api, fields, models



class ParameterChatterPolicyPreview(models.TransientModel):
    _name = "parameter.chatter.policy.preview"
    _description = "Chatter Workspace effective layout check"

    user_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user,
        domain=[("share", "=", False)],
    )
    model_id = fields.Many2one(
        "ir.model", string="Form", required=True, ondelete="cascade",
        domain=[("transient", "=", False)],
        default=lambda self: self.env["ir.model"]._get("res.partner"),
    )
    rule_id = fields.Many2one("parameter.chatter.rule", compute="_compute_result", string="Winning Rule")
    result_html = fields.Html(compute="_compute_result", sanitize=True)

    @api.depends("user_id", "model_id")
    def _compute_result(self):
        policy = self.env["parameter.chatter.policy"]
        source_labels = {
            "model": _("Personal layout for this form"),
            "personal": _("Personal default"),
            "rule": _("Team default rule"),
            "settings": _("Global setting"),
            "product": _("Odoo standard"),
            "feature": _("Feature disabled"),
        }
        for wizard in self:
            if not wizard.user_id or not wizard.model_id:
                wizard.rule_id = False
                wizard.result_html = False
                continue
            config = policy._compute_effective(wizard.user_id, wizard.model_id.model)
            wizard.rule_id = config["rule"] and config["rule"]["id"]
            eff, src = config["effective"], config["sources"]
            rows = [
                (_("Layout"), eff["layout"], src["layout"]),
                (_("Chatter"), eff["dock_state"], src["dock_state"]),
                (_("Standard width"), eff["width"] or _("Odoo default"), src["width"]),
                (_("Conversation width"), eff["conversation_width"] or _("Automatic"), src["conversation_width"]),
                (_("Review width"), eff["review_width"] or _("Automatic"), src["review_width"]),
            ]
            body = "".join(
                f"<tr><td>{escape(label)}</td><td><strong>{escape(value)}</strong></td>"
                f"<td>{escape(source_labels[source])}</td></tr>"
                for label, value, source in rows
            )
            locks = []
            if config["locks"]["layout"]:
                locks.append(_("layout locked"))
            if config["locks"]["width"]:
                locks.append(_("width locked"))
            wizard.result_html = Markup(
                f"<table class='table table-sm'><thead><tr><th>{escape(_('Setting'))}</th>"
                f"<th>{escape(_('Value'))}</th><th>{escape(_('Comes from'))}</th></tr></thead><tbody>{body}</tbody></table>"
                f"<p>{escape(_('Locks'))}: {escape(', '.join(locks) or _('none'))}</p>"
            )
