# -*- coding: utf-8 -*-
"""
Fit every invoice a check pays on the one check sheet.

Odoo's US check report splits the remittance stub into pages of
``INV_LINES_PER_STUB`` (9) invoices. UFS's pre-printed stock fits about 8
at the default 10pt, and a second page is stub-only, which lands on the
next blank check in the printer. Jeff pays his big vendors 10 or more
invoices per check, so the stub must shrink instead of overflowing.

Two pieces do that:

* This file raises the per-stub limit to ``UFS_STUB_MAX_LINES`` so the
  report keeps everything on one stub up to that count (the company's
  "Multi-Pages Check Stub" setting stays on, so a check beyond the limit
  still spills to a second page rather than being cut off).
* ``views/check_layout_tweaks.xml`` tags each stub with a size tier from
  the number of lines it carries and scales the stub table's font and row
  height per tier (font-size and line-height only: wkhtmltopdf drops CSS
  transforms).

Tiers (lines per stub -> tier): up to 8 -> n (10pt, unchanged), 9-11 -> s
(8.5pt), 12-14 -> m (7.5pt), 15-18 -> l (6.5pt), 19-24 -> xl (5.5pt).
"""
import logging

_logger = logging.getLogger(__name__)

UFS_STUB_MAX_LINES = 24

try:
    from odoo.addons.l10n_us_check_printing.models import account_payment as _us_check
    _us_check.INV_LINES_PER_STUB = UFS_STUB_MAX_LINES
except Exception:  # pragma: no cover - module layout changed upstream
    _logger.warning("ufs_customizations: could not raise INV_LINES_PER_STUB; check stubs keep Odoo's default page size")
