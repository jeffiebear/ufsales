# -*- coding: utf-8 -*-
"""
Loader for the normalized Step1 header export.

Accounting managers upload the per-fiscal-year CSVs (any number at
once; each file is 1,000 to 7,000 rows and loads in a few seconds). Rows whose Step1 invoice id already exists are skipped,
so a file can be re-uploaded safely. Column names must match the model
field names produced by ``normalize_headers.py``.
"""
import base64
import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError


class UfsStep1Import(models.TransientModel):
    _name = "ufs.step1.import"
    _description = "Load Step1 Invoice History"

    attachment_ids = fields.Many2many("ir.attachment", string="Normalized CSV files", required=True,
                                      help="One or more per-fiscal-year files from normalize_headers.py. Any number at once.")
    result = fields.Text(readonly=True)

    _COLS = (
        "invoice_num order_num order_date date_shipped invoice_date due_date terms cust_po cust_acct "
        "customer_name salesperson tax_area tax_rate tax_flag warehouse merch_total taxable_sales "
        "nontaxable_sales sales_tax freight total_due ave_costs status posted_flag trans_type trans_source "
        "fiscal_year post_period pmt_date entered_ts entered_by cust_id arinvc_id source_file"
    ).split()
    _DATES = {"order_date", "date_shipped", "invoice_date", "due_date", "pmt_date"}
    _FLOATS = {"tax_rate", "merch_total", "taxable_sales", "nontaxable_sales", "sales_tax", "freight", "total_due", "ave_costs"}

    def action_load(self):
        self.ensure_one()
        Invoice = self.env["ufs.step1.invoice"]
        lines = []
        for att in self.attachment_ids.sorted("name"):
            text = base64.b64decode(att.datas).decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            missing = [c for c in ("arinvc_id", "invoice_num", "trans_type") if c not in (reader.fieldnames or [])]
            if missing:
                raise UserError(_("%(file)s does not look like the normalized header export (missing %(cols)s).",
                                  file=att.name, cols=", ".join(missing)))
            existing = set(Invoice.search([]).mapped("arinvc_id")) if Invoice.search_count([]) else set()
            vals_list, skipped, bad = [], 0, 0
            for row in reader:
                key = (row.get("arinvc_id") or "").strip()
                if not key or key in existing:
                    skipped += 1
                    continue
                if row.get("trans_type") not in ("IN", "CM", "DS", "CS"):
                    bad += 1
                    continue
                vals = {}
                for col in self._COLS:
                    if col not in row:
                        continue
                    val = (row[col] or "").strip()
                    if col in self._DATES:
                        vals[col] = val or False
                    elif col in self._FLOATS:
                        vals[col] = float(val or 0)
                    else:
                        vals[col] = val
                vals["paid_flag"] = (row.get("paid_flag") or "").strip().upper() == "Y"
                vals_list.append(vals)
                existing.add(key)
            created = 0
            for i in range(0, len(vals_list), 1000):
                created += len(Invoice.create(vals_list[i:i + 1000]))
            lines.append(_("%(file)s: %(created)s loaded, %(skipped)s already present, %(bad)s rejected.",
                           file=att.name, created=created, skipped=skipped, bad=bad))
        lines.append(_("Archive now holds %(total)s documents, %(unlinked)s without an Odoo customer.",
                       total=Invoice.search_count([]), unlinked=Invoice.search_count([("partner_id", "=", False)])))
        self.result = "\n".join(lines)
        self.attachment_ids.unlink()
        return {
            "type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
            "view_mode": "form", "target": "new",
        }
