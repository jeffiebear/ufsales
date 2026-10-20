# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
{
    "name": "Chatter Workspace",
    "summary": "Resize, collapse (hide) or float the chatter on Odoo forms: Data Entry, "
    "Conversation and Review layouts, per-user layouts and team defaults.",
    "description": """
Chatter Workspace
=================
Arrange the form, the chatter and Odoo's document preview for the task at hand:
resize the side chatter, collapse it into a slim strip, move it into a floating
panel inside the page, or pick a Data Entry, Conversation or Review layout.
Layouts are saved per user on the server, per form type where configured.
Administrators set defaults, width limits, feature availability and locks,
including rules by model and user group.
""",
    "version": "19.0.1.0.0",
    "category": "Productivity/Discuss",
    "author": "Parameter",
    "website": "https://parameterllc.com/",
    "support": "support@parameterllc.com",
    "maintainer": "Parameter",
    "license": "LGPL-3",
    "depends": ["mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/chatter_rule_views.xml",
        "views/chatter_preference_views.xml",
        "wizard/policy_preview_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "parameter_chatter_resize/static/src/layout_math.js",
            "parameter_chatter_resize/static/src/form_compiler_patch.js",
            "parameter_chatter_resize/static/src/chatter_workspace.js",
            "parameter_chatter_resize/static/src/chatter_workspace.scss",
        ],
    },
    "images": [
        "static/description/main_screenshot.png",
    ],
    # One-time price per Odoo major version, confirmed by the owner on 2026-10-20.
    "price": 29.0,
    "currency": "USD",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
}
