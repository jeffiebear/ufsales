# Re-stamp PO Confirmation Date (date_approve) and Expected Arrival
# (date_planned) from the STEP1 export, for the imported POs.
#
# WHY: the importer set these from STEP1 DateReceived / ExpReceiveDate,
# but confirming each PO during import overwrote date_approve with the
# import timestamp (Jul 2026) and re-defaulted date_planned. The true
# order date (date_order) survived and is already correct — only these
# two display dates need to be re-applied from the source CSV.
#
# Matches Odoo POs to the CSV on
#   purchase.order.ufs_step1_po_number == po_summary.PONumber
# (the same idempotent key the importer used).
#
# Run in the Odoo shell (Odoo.sh: Shell tab, or `odoo-bin shell`):
#   exec(open('/home/odoo/src/user/scripts/restamp_po_dates_from_step1.py').read())
#
# SAFE BY DEFAULT: DRY_RUN=True only reports counts. Set DRY_RUN=False
# to write. Re-runnable: it skips POs whose dates already match.

import csv
import os
from datetime import datetime

DRY_RUN = True          # <-- set False to actually write
BATCH = 500             # commit cadence


def _s(v):
    return (v or "").strip()


def _to_date(v):
    """Mirror of the importer's date parser (M/D/Y and friends)."""
    s = _s(v)
    if not s:
        return False
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return False


# --- locate the STEP1 PO summary CSV shipped with the import module ----
csv_path = None
try:
    from odoo.tools import file_path
    csv_path = file_path("ufsales_product_import/data/po_summary.csv")
except Exception:
    from odoo.modules.module import get_module_path
    csv_path = os.path.join(
        get_module_path("ufsales_product_import"), "data", "po_summary.csv")
print("Reading:", csv_path)

# pono -> (DateReceived, ExpReceiveDate)
src = {}
with open(csv_path, newline="", encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        pono = _s(row.get("PONumber"))
        if pono:
            src[pono] = (
                _to_date(row.get("DateReceived")),
                _to_date(row.get("ExpReceiveDate")),
            )
print("STEP1 PO rows:", len(src))

PO = env["purchase.order"].sudo()
po_ids = PO.search([("ufs_step1_po_number", "!=", False)]).ids
print("Imported POs in Odoo:", len(po_ids))

updated = approve_set = planned_set = missing = 0
for i in range(0, len(po_ids), BATCH):
    for po in PO.browse(po_ids[i:i + BATCH]):
        rec = src.get(po.ufs_step1_po_number)
        if not rec:
            missing += 1
            continue
        d_recv, d_exp = rec
        touched = False

        # Confirmation Date <- STEP1 DateReceived (header, always writable)
        if d_recv and (not po.date_approve or po.date_approve.date() != d_recv):
            if not DRY_RUN:
                po.date_approve = datetime.combine(d_recv, datetime.min.time())
            approve_set += 1
            touched = True

        # Expected Arrival <- STEP1 ExpReceiveDate. Written on the lines
        # (purchase.order.line.date_planned is a plain stored field); the
        # header "Expected Arrival" recomputes from the lines.
        if d_exp:
            want = datetime.combine(d_exp, datetime.min.time())
            bad = po.order_line.filtered(
                lambda l: not l.date_planned or l.date_planned.date() != d_exp)
            if bad:
                if not DRY_RUN:
                    bad.date_planned = want
                planned_set += 1
                touched = True

        if touched:
            updated += 1

    if not DRY_RUN:
        env.cr.commit()
    print("  processed %s/%s (updated so far: %s)" % (
        min(i + BATCH, len(po_ids)), len(po_ids), updated))

print("---")
print("POs updated        :", updated)
print("  date_approve set  :", approve_set)
print("  date_planned set  :", planned_set)
print("no STEP1 match      :", missing)
print("DRY_RUN             :", DRY_RUN,
      "(nothing written)" if DRY_RUN else "(changes committed)")
