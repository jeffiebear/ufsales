# -*- coding: utf-8 -*-
"""
Step1 customer invoice history (header level), loaded once from the
legacy system's export at the June 30, 2026 cutover.

Design notes
------------
* Pure reference data. No journal entries, no account.move, nothing in
  financial reports. Amounts are plain floats copied from Step1.
* ``arinvc_id`` is Step1's stable primary key and is unique here, so
  the loader can be re-run safely (create-or-skip).
* ``partner_id`` is resolved from the Step1 account code (``cust_acct``)
  against ``res.partner.ref``. Company partners win over contacts when a
  code is duplicated. Unmatched rows keep ``customer_name`` and can be
  re-linked later with :meth:`action_link_partners`.
* Users get read access only. Accounting managers can delete/reload.
"""
from odoo import api, fields, models


class UfsStep1Invoice(models.Model):
    _name = "ufs.step1.invoice"
    _description = "Step1 Invoice History"
    _order = "invoice_date desc, invoice_num desc"
    _rec_name = "invoice_num"

    invoice_num = fields.Char("Invoice #", required=True, index=True)
    order_num = fields.Char("Order #")
    arinvc_id = fields.Char("Step1 Invoice ID", required=True, index=True,
                            help="vCustomerInvoiceSummary.ARInvcID, Step1's stable key.")
    trans_type = fields.Selection([
        ("IN", "Invoice"), ("CM", "Credit Memo"), ("DS", "Drop Ship"), ("CS", "Counter Sale"),
    ], string="Type", required=True, index=True)
    trans_source = fields.Char("Source")

    partner_id = fields.Many2one("res.partner", string="Customer", index=True, ondelete="set null")
    cust_acct = fields.Char("Step1 Account", index=True)
    cust_id = fields.Char("Step1 Customer ID")
    customer_name = fields.Char("Customer Name (Step1)", index=True)
    cust_po = fields.Char("Customer PO")
    salesperson = fields.Char("Territory", help="Step1 route/territory (Westside, Southside, ...).")

    order_date = fields.Date("Order Date")
    date_shipped = fields.Date("Shipped")
    invoice_date = fields.Date("Invoice Date", index=True)
    due_date = fields.Date("Due Date")
    terms = fields.Char("Terms")
    fiscal_year = fields.Char("Fiscal Year", index=True)
    post_period = fields.Char("Period")

    merch_total = fields.Float("Merchandise", digits=(16, 2))
    taxable_sales = fields.Float("Taxable", digits=(16, 2))
    nontaxable_sales = fields.Float("Non-taxable", digits=(16, 2))
    sales_tax = fields.Float("Sales Tax", digits=(16, 2))
    freight = fields.Float("Freight", digits=(16, 2))
    total_due = fields.Float("Total", digits=(16, 2))
    ave_costs = fields.Float("Cost (Step1 avg)", digits=(16, 2))
    tax_area = fields.Char("Tax Area")
    tax_rate = fields.Float("Tax Rate", digits=(6, 3))
    tax_flag = fields.Char("Taxable Flag")
    warehouse = fields.Char("Warehouse")

    paid_flag = fields.Boolean("Paid in Step1")
    pmt_date = fields.Date("Paid On")
    status = fields.Char("Step1 Status")
    posted_flag = fields.Char("Posted Flag")
    entered_by = fields.Char("Entered By")
    entered_ts = fields.Char("Entered At")
    source_file = fields.Char("Source File")

    open_at_cutover = fields.Boolean(
        "Open at June 30, 2026", compute="_compute_open_at_cutover", store=True,
        help="Not paid in Step1 by the cutover date. These documents were also loaded as "
             "real opening receivables (invoice_origin STEP1-OB), where payments are applied.")

    _arinvc_id_uniq = models.Constraint("unique(arinvc_id)", "This Step1 invoice is already in the archive.")

    @api.depends("paid_flag", "pmt_date")
    def _compute_open_at_cutover(self):
        cutover = fields.Date.to_date("2026-06-30")
        for rec in self:
            rec.open_at_cutover = not rec.paid_flag or (rec.pmt_date and rec.pmt_date > cutover)

    @api.depends("invoice_num", "trans_type")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.invoice_num} ({dict(rec._fields['trans_type'].selection).get(rec.trans_type, rec.trans_type)})"

    @api.model
    def _partner_for_code(self, code):
        """Company partner whose Reference equals the Step1 account code; contacts as fallback."""
        if not code:
            return self.env["res.partner"]
        Partner = self.env["res.partner"].with_context(active_test=False)
        return (Partner.search([("ref", "=", code), ("is_company", "=", True)], limit=1)
                or Partner.search([("ref", "=", code)], limit=1))

    @api.model_create_multi
    def create(self, vals_list):
        cache = {}
        for vals in vals_list:
            code = vals.get("cust_acct")
            if code and not vals.get("partner_id"):
                if code not in cache:
                    cache[code] = self._partner_for_code(code).id
                vals["partner_id"] = cache[code]
        return super().create(vals_list)

    def action_link_partners(self):
        """Re-resolve customers for records without a partner (after refs are fixed)."""
        cache = {}
        for rec in self.filtered(lambda r: not r.partner_id and r.cust_acct):
            if rec.cust_acct not in cache:
                cache[rec.cust_acct] = self._partner_for_code(rec.cust_acct).id
            if cache[rec.cust_acct]:
                rec.partner_id = cache[rec.cust_acct]
