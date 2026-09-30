# -*- coding: utf-8 -*-
"""
Fit every invoice a check pays on the one check sheet.

Odoo's check printing (``account_check_printing``) crops the remittance
stub at ``INV_LINES_PER_STUB`` (9) lines, showing 8 and an ellipsis. The
alternative, the company's "Multi-Pages Check Stub" setting, prints the
rest on a stub-only second page, which lands on the next blank check in
the printer. Jeff pays his big vendors 10 or more invoices per check, so
the stub must shrink to fit instead.

Two pieces do that (with "Multi-Pages Check Stub" left OFF):

* This file raises the per-stub limit to ``UFS_STUB_MAX_LINES`` so the
  stub lists up to that many lines on the one sheet. Beyond it, Odoo's
  normal crop applies (first 23 and an ellipsis).
* ``views/check_layout_tweaks.xml`` tags each stub with a size tier from
  the number of lines it carries and scales the stub table's font and row
  height per tier (font-size and line-height only: wkhtmltopdf drops CSS
  transforms).

Tiers (lines per stub -> tier): up to 10 -> n (full size, unchanged),
11-13 -> s (9pt), 14-16 -> m (8pt), 17-20 -> l (7pt), 21-24 -> xl (6pt).
"""
import logging

_logger = logging.getLogger(__name__)

UFS_STUB_MAX_LINES = 24

try:
    # Odoo 19 keeps the constant in the base check module; the US layout only renders it.
    from odoo.addons.account_check_printing.models import account_payment as _check_payment
    _check_payment.INV_LINES_PER_STUB = UFS_STUB_MAX_LINES
except Exception:  # pragma: no cover - module layout changed upstream
    _logger.warning("ufs_customizations: could not raise INV_LINES_PER_STUB; check stubs keep Odoo's default size")
