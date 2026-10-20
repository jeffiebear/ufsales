# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
"""Let this module's views be created during an upgrade on Odoo 20 + Website.

Odoo 20's website app makes ``ir_ui_view.visibility`` NOT NULL without a
database default. This module does not depend on website, so during its
upgrade it is loaded before website, its new views are inserted without that
column and PostgreSQL refuses them. For the duration of this upgrade the
column gets website's own default ('public'); the end-migration removes it.
Runs on every version change (folder 0.0.0); does nothing elsewhere.
"""

MARKER = "parameter_chatter_resize.view_visibility_default"


def migrate(cr, version):
    cr.execute(
        """SELECT is_nullable, column_default FROM information_schema.columns
           WHERE table_schema = current_schema() AND table_name = 'ir_ui_view'
             AND column_name = 'visibility'"""
    )
    row = cr.fetchone()
    if not row or row[0] != "NO" or row[1] is not None:
        return
    cr.execute("ALTER TABLE ir_ui_view ALTER COLUMN visibility SET DEFAULT 'public'")
    cr.execute(
        """INSERT INTO ir_config_parameter (key, value, create_date, write_date)
           VALUES (%s, 'set', now() at time zone 'UTC', now() at time zone 'UTC')
           ON CONFLICT (key) DO UPDATE SET value = 'set'""",
        [MARKER],
    )
