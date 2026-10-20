# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from . import models
from . import wizard

PARAM_PREFIX = "parameter_chatter_resize."


def uninstall_hook(env):
    """Remove the module's settings. Preference and rule tables are dropped by Odoo."""
    env["ir.config_parameter"].sudo().search([("key", "=like", PARAM_PREFIX + "%")]).unlink()
