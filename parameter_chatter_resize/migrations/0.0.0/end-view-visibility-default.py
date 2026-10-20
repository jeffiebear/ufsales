# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
"""Remove the temporary ``ir_ui_view.visibility`` default set by the
pre-migration (see pre-view-visibility-default.py), only if it set one."""

MARKER = "parameter_chatter_resize.view_visibility_default"


def migrate(cr, version):
    cr.execute("DELETE FROM ir_config_parameter WHERE key = %s RETURNING id", [MARKER])
    if cr.fetchone():
        cr.execute("ALTER TABLE ir_ui_view ALTER COLUMN visibility DROP DEFAULT")
